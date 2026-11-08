"""Hash-chained audit log with HMAC anchors.

Each row stores sha256(canonical(row without hash)) and the previous row's hash.
Editing a row breaks its hash; deleting a row breaks the sequence; cutting the
tail is caught by the anchors (one write-once file every N rows, HMAC-signed).
The anchor folder is watched by Wazuh FIM.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from .db import Repo
from .schemas import canonical_json, sha256_hex, utcnow

GENESIS = "0" * 64


class AuditChain:
    def __init__(self, repo: Repo, anchor_dir: Path, anchor_key: bytes, anchor_every: int = 20):
        self.repo = repo
        self.anchor_root = anchor_dir
        self.anchor_key = anchor_key
        self.anchor_every = anchor_every

    @property
    def anchor_dir(self) -> Path:
        """One write-once folder per database epoch: a demo reset never rewrites old anchors."""
        folder = self.anchor_root / self.repo.epoch
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _record(seq: int, ts: str, tenant_id: str, actor: str, action: str, decision: str | None,
                data: dict[str, Any], prev_hash: str) -> dict[str, Any]:
        return {"seq": seq, "ts": ts, "tenant_id": tenant_id, "actor": actor, "action": action,
                "decision": decision, "data": data, "prev_hash": prev_hash}

    def append(self, *, tenant_id: str, actor: str, action: str, decision: str | None = None,
               data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.loads(canonical_json(data or {}))
        with self.repo.tx() as c:
            row = c.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            seq = (row["seq"] + 1) if row else 1
            ts = utcnow().isoformat()
            record = self._record(seq, ts, tenant_id, actor, action, decision, data, prev)
            digest = sha256_hex(canonical_json(record))
            c.execute(
                "INSERT INTO audit_log (seq, ts, tenant_id, actor, action, decision, data, prev_hash, hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (seq, ts, tenant_id, actor, action, decision, canonical_json(data), prev, digest),
            )
        if seq % self.anchor_every == 0:
            self.write_anchor(seq, digest)
        return {**record, "hash": digest}

    # -- anchors -------------------------------------------------------------------------
    def _mac(self, seq: int, digest: str) -> str:
        return hmac.new(self.anchor_key, f"{seq}:{digest}".encode(), hashlib.sha256).hexdigest()

    def write_anchor(self, seq: int | None = None, digest: str | None = None) -> Path | None:
        if seq is None or digest is None:
            rows = self.repo.q("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1")
            if not rows:
                return None
            seq, digest = rows[0]["seq"], rows[0]["hash"]
        path = self.anchor_dir / f"anchor_{seq:08d}.json"
        if not path.exists():  # write-once: Wazuh alerts on modify/delete, not on add
            path.write_text(json.dumps({"seq": seq, "hash": digest, "ts": utcnow().isoformat(), "mac": self._mac(seq, digest)}))
        return path

    def _anchors(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.anchor_dir.glob("anchor_*.json")):
            try:
                out.append({**json.loads(path.read_text()), "file": path.name})
            except (OSError, ValueError):
                out.append({"file": path.name, "broken": True})
        return out

    # -- verify ----------------------------------------------------------------------------
    def verify(self) -> dict[str, Any]:
        rows = self.repo.q("SELECT * FROM audit_log ORDER BY seq")
        prev, expected = GENESIS, 1
        hashes: dict[int, str] = {}
        result: dict[str, Any] = {"ok": True, "checked": 0, "first_bad_seq": None, "reason": None, "anchors_ok": True}
        for r in rows:
            if r["seq"] != expected:
                return {**result, "ok": False, "first_bad_seq": expected, "reason": "row missing (sequence gap)", "checked": expected - 1}
            if r["prev_hash"] != prev:
                return {**result, "ok": False, "first_bad_seq": r["seq"], "reason": "prev_hash does not match", "checked": expected - 1}
            record = self._record(r["seq"], r["ts"], r["tenant_id"], r["actor"], r["action"], r["decision"],
                                  json.loads(r["data"]), r["prev_hash"])
            if sha256_hex(canonical_json(record)) != r["hash"]:
                return {**result, "ok": False, "first_bad_seq": r["seq"], "reason": "row content was modified", "checked": expected - 1}
            hashes[r["seq"]] = r["hash"]
            prev, expected = r["hash"], expected + 1
        result["checked"] = len(rows)
        result["head"] = prev
        for a in self._anchors():
            if a.get("broken") or not hmac.compare_digest(a.get("mac", ""), self._mac(a.get("seq", -1), a.get("hash", ""))):
                return {**result, "ok": False, "anchors_ok": False, "reason": f"anchor {a['file']} is not authentic"}
            if a["seq"] not in hashes:
                return {**result, "ok": False, "anchors_ok": False, "first_bad_seq": a["seq"], "reason": "log is shorter than an anchor (tail deleted)"}
            if hashes[a["seq"]] != a["hash"]:
                return {**result, "ok": False, "anchors_ok": False, "first_bad_seq": a["seq"], "reason": "anchor hash does not match the log"}
        result["anchors"] = len(self._anchors())
        return result

    def recent(self, limit: int = 50, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if tenant_id:
            rows = self.repo.q("SELECT * FROM audit_log WHERE tenant_id IN (?, '*') ORDER BY seq DESC LIMIT ?", (tenant_id, limit))
        else:
            rows = self.repo.q("SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,))
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    # -- demo only -----------------------------------------------------------------------------
    def tamper_one_row(self) -> int | None:
        """Change one past row in place (what an insider would do). Verify must turn red."""
        rows = self.repo.q("SELECT seq, data FROM audit_log WHERE action LIKE 'payment.%' ORDER BY seq DESC LIMIT 1")
        if not rows:
            rows = self.repo.q("SELECT seq, data FROM audit_log ORDER BY seq DESC LIMIT 1 OFFSET 1")
        if not rows:
            return None
        seq, data = rows[0]["seq"], json.loads(rows[0]["data"])
        if "amount_millimes" in data:
            data["amount_millimes"] = 1000  # "it was only 1 TND"
        else:
            data["tampered"] = True
        self.repo.x("UPDATE audit_log SET data=? WHERE seq=?", (canonical_json(data), seq))
        return seq
