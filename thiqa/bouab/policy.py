"""Permission matrix: loaded once, signature-checked, invariants enforced in code."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..schemas import AgentId, Tool, sha256_hex

# These hold whatever policy.yaml says. Changing them needs a code review, not a YAML edit.
NEVER_GRANTABLE = {Tool.SCRIPT_ACTIVATE.value, Tool.CATALOG_WRITE.value, Tool.POLICY_WRITE.value,
                   Tool.APPROVAL_GRANT.value, Tool.DB_QUERY.value}
EXCLUSIVE = {Tool.PAY_CREATE_INTENT.value: {AgentId.SANDOUK.value}}
KNOWN_AGENTS = {a.value for a in AgentId}


def sign_bytes(raw: bytes, key: bytes) -> str:
    return hmac.new(key, raw, hashlib.sha256).hexdigest()


def sig_path_for(path: Path) -> Path:
    return path.with_name(path.name + ".sig")


@dataclass
class Policy:
    path: Path
    sha256: str
    signature: str                      # valid | invalid | missing | unsigned-dev
    fail_closed: bool
    matrix: dict[str, frozenset[str]]
    sensitive: frozenset[str]
    kill_switch: dict[str, int]
    version: int
    problems: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path, key: bytes | None) -> "Policy":
        raw = path.read_bytes()
        sha = sha256_hex(raw)
        sig_file = sig_path_for(path)
        if key is None:
            signature = "unsigned-dev"
        elif not sig_file.exists():
            signature = "missing"
        else:
            signature = "valid" if hmac.compare_digest(sig_file.read_text().strip(), sign_bytes(raw, key)) else "invalid"

        problems: list[str] = []
        matrix: dict[str, frozenset[str]] = {}
        sensitive: frozenset[str] = frozenset({Tool.PAY_CREATE_INTENT.value})
        kill_switch = {"denied_calls": 3, "window_seconds": 60, "burst_calls": 40, "burst_window_seconds": 10}
        version = 0
        try:
            data = yaml.safe_load(raw) or {}
            version = int(data.get("version", 0))
            for agent, tools in (data.get("agents") or {}).items():
                if agent not in KNOWN_AGENTS:
                    problems.append(f"unknown agent '{agent}' ignored")
                    continue
                granted = set()
                for tool in tools or []:
                    if tool in NEVER_GRANTABLE:
                        problems.append(f"{agent}: '{tool}' can never be granted to an agent (dropped)")
                    elif tool in EXCLUSIVE and agent not in EXCLUSIVE[tool]:
                        problems.append(f"{agent}: '{tool}' belongs to {sorted(EXCLUSIVE[tool])} only (dropped)")
                    else:
                        granted.add(str(tool))
                matrix[agent] = frozenset(granted)
            sensitive = frozenset(data.get("sensitive_tools") or sensitive) | {Tool.PAY_CREATE_INTENT.value}
            kill_switch.update({k: int(v) for k, v in (data.get("kill_switch") or {}).items()})
        except Exception as exc:  # unreadable policy -> fail closed
            problems.append(f"policy unreadable: {exc.__class__.__name__}")
            signature = "invalid" if signature != "unsigned-dev" else signature
            matrix = {}

        fail_closed = signature in ("invalid", "missing") or not matrix
        if fail_closed:
            problems.append(f"fail-closed: signature {signature}; every agent tool is denied")
        return cls(path=path, sha256=sha, signature=signature, fail_closed=fail_closed,
                   matrix={} if fail_closed else matrix, sensitive=sensitive, kill_switch=kill_switch,
                   version=version, problems=problems)

    def allowed(self, agent_id: str, tool: str) -> bool:
        if self.fail_closed or tool in NEVER_GRANTABLE:
            return False
        if tool in EXCLUSIVE and agent_id not in EXCLUSIVE[tool]:
            return False
        return tool in self.matrix.get(agent_id, frozenset())

    def disk_sha256(self) -> str | None:
        try:
            return sha256_hex(self.path.read_bytes())
        except OSError:
            return None

    def as_dict(self) -> dict:
        return {
            "version": self.version, "sha256": self.sha256, "signature": self.signature,
            "fail_closed": self.fail_closed, "problems": self.problems,
            "matrix": {a: sorted(t) for a, t in self.matrix.items()},
            "sensitive_tools": sorted(self.sensitive), "never_grantable": sorted(NEVER_GRANTABLE),
            "exclusive": {k: sorted(v) for k, v in EXCLUSIVE.items()}, "kill_switch": self.kill_switch,
        }
