"""SQLite (WAL) behind a repository layer. tenant_id is on every table.

One process, one connection, one lock: enough for the demo. Production path is
PostgreSQL + outbox + row-level security behind the same methods.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .schemas import (
    Approval,
    ApprovalStatus,
    CaseFile,
    EventEnvelope,
    PaymentIntent,
    Recommendation,
    RiskSignal,
    ScriptVersion,
    ToolDecision,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT, customer_ref TEXT NOT NULL,
  state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_cases_tenant ON cases(tenant_id, run_id);

CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL, case_id TEXT, run_id TEXT, type TEXT NOT NULL, source TEXT NOT NULL,
  decision TEXT, severity TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_tenant ON events(tenant_id, seq);
CREATE INDEX IF NOT EXISTS ix_events_case ON events(case_id);

CREATE TABLE IF NOT EXISTS payments (
  payment_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL, run_id TEXT,
  amount_millimes INTEGER NOT NULL CHECK (amount_millimes > 0), currency TEXT NOT NULL,
  method TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
  idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_payments_tenant ON payments(tenant_id, run_id);

CREATE TABLE IF NOT EXISTS ledger_lines (
  line_id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
  run_id TEXT, payment_id TEXT, account TEXT NOT NULL,
  debit_millimes INTEGER NOT NULL DEFAULT 0, credit_millimes INTEGER NOT NULL DEFAULT 0, ts TEXT NOT NULL,
  CHECK (debit_millimes >= 0 AND credit_millimes >= 0),
  CHECK ((debit_millimes = 0) <> (credit_millimes = 0)));
CREATE INDEX IF NOT EXISTS ix_ledger_tenant ON ledger_lines(tenant_id, entry_id);

CREATE TABLE IF NOT EXISTS audit_log (
  seq INTEGER PRIMARY KEY, ts TEXT NOT NULL, tenant_id TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, decision TEXT, data TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL, run_id TEXT,
  customer_ref TEXT, agent_id TEXT NOT NULL, action TEXT NOT NULL, decision TEXT NOT NULL,
  idem_key TEXT, method TEXT, risk_score INTEGER NOT NULL, ts_epoch REAL NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_decisions_idem ON decisions(idem_key);
CREATE INDEX IF NOT EXISTS ix_decisions_customer ON decisions(tenant_id, customer_ref, ts_epoch);

CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, doc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS used_authorizations (jti TEXT PRIMARY KEY, payment_id TEXT, used_at REAL NOT NULL);

CREATE TABLE IF NOT EXISTS risk_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL,
  customer_ref TEXT, code TEXT NOT NULL, weight INTEGER NOT NULL, ts_epoch REAL NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_signals_case ON risk_signals(case_id);

CREATE TABLE IF NOT EXISTS quarantine_inputs (
  qid TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL, ts TEXT NOT NULL,
  text_sha256 TEXT NOT NULL, reasons TEXT NOT NULL, text TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS agent_quarantine (
  agent_id TEXT NOT NULL, case_id TEXT NOT NULL, tenant_id TEXT NOT NULL, reason TEXT NOT NULL,
  requested_by TEXT NOT NULL, ts TEXT NOT NULL, lifted_by TEXT, lifted_at TEXT,
  PRIMARY KEY (agent_id, case_id, ts));

CREATE TABLE IF NOT EXISTS scripts (
  tenant_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, doc TEXT NOT NULL,
  PRIMARY KEY (tenant_id, version));

CREATE TABLE IF NOT EXISTS recommendations (
  rec_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT, ts TEXT NOT NULL, doc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS security_alerts (
  alert_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, ts TEXT NOT NULL, source TEXT NOT NULL,
  type TEXT NOT NULL, severity TEXT NOT NULL, run_id TEXT, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_alerts_tenant ON security_alerts(tenant_id, ts);

CREATE TABLE IF NOT EXISTS kpi_snapshots (
  snap_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, scope TEXT NOT NULL, ts TEXT NOT NULL, doc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, ts TEXT NOT NULL, doc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

DATA_TABLES = [
    "cases", "events", "payments", "ledger_lines", "audit_log", "decisions", "approvals",
    "used_authorizations", "risk_signals", "quarantine_inputs", "agent_quarantine",
    "recommendations", "security_alerts", "kpi_snapshots", "runs", "scripts",
]


def _iso(dt) -> str:
    return dt.isoformat()


class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=10)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)
            if not self.q("SELECT value FROM meta WHERE key='epoch'"):
                self.x("INSERT INTO meta (key, value) VALUES ('epoch', ?)", (uuid.uuid4().hex[:12],))

    @property
    def epoch(self) -> str:
        return self.q("SELECT value FROM meta WHERE key='epoch'")[0]["value"]

    # -- plumbing -------------------------------------------------------------
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def q(self, sql: str, args: tuple | list = ()) -> list[sqlite3.Row]:
        with self.lock:
            return list(self.conn.execute(sql, args))

    def x(self, sql: str, args: tuple | list = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, args)

    def reset(self) -> None:
        with self.tx() as c:
            for table in DATA_TABLES:
                c.execute(f"DELETE FROM {table}")  # nosec B608 - table names come from the DATA_TABLES constant
            c.execute("DELETE FROM sqlite_sequence")
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('epoch', ?)", (uuid.uuid4().hex[:12],))

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # -- cases (written only by the orchestrator) ----------------------------
    def save_case(self, case: CaseFile) -> None:
        self.x(
            "INSERT INTO cases (case_id, tenant_id, run_id, customer_ref, state, created_at, updated_at, doc) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET state=excluded.state, "
            "updated_at=excluded.updated_at, doc=excluded.doc",
            (case.case_id, case.tenant_id, case.run_id, case.customer_ref, case.state.value,
             _iso(case.created_at), _iso(case.updated_at), case.model_dump_json()),
        )

    def get_case(self, case_id: str) -> CaseFile | None:
        rows = self.q("SELECT doc FROM cases WHERE case_id=?", (case_id,))
        return CaseFile.model_validate_json(rows[0]["doc"]) if rows else None

    def list_cases(self, tenant_id: str, run_id: str | None = None) -> list[CaseFile]:
        if run_id is None:
            rows = self.q("SELECT doc FROM cases WHERE tenant_id=? AND run_id IS NULL ORDER BY created_at", (tenant_id,))
        else:
            rows = self.q("SELECT doc FROM cases WHERE tenant_id=? AND run_id=? ORDER BY created_at", (tenant_id, run_id))
        return [CaseFile.model_validate_json(r["doc"]) for r in rows]

    # -- events ----------------------------------------------------------------
    def insert_event(self, ev: EventEnvelope) -> int:
        cur = self.x(
            "INSERT INTO events (event_id, ts, tenant_id, case_id, run_id, type, source, decision, severity, doc) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ev.event_id, _iso(ev.ts), ev.tenant_id, ev.case_id, ev.run_id, ev.type.value, ev.source,
             ev.decision.value if ev.decision else None, ev.severity.value, ev.model_dump_json(exclude={"seq"})),
        )
        return int(cur.lastrowid)

    def list_events(self, tenant_id: str | None, after_seq: int = 0, limit: int = 200,
                    include_runs: bool = False, case_id: str | None = None, run_id: str | None = None) -> list[EventEnvelope]:
        sql = "SELECT seq, doc FROM events WHERE seq > ?"
        args: list[Any] = [after_seq]
        if tenant_id:
            sql += " AND tenant_id = ?"
            args.append(tenant_id)
        if case_id:
            sql += " AND case_id = ?"
            args.append(case_id)
        if run_id:
            sql += " AND run_id = ?"
            args.append(run_id)
        elif not include_runs:
            sql += " AND (run_id IS NULL OR substr(run_id, 1, 4) <> 'run_')"
        sql += " ORDER BY seq LIMIT ?"
        args.append(min(max(limit, 1), 2000))
        out = []
        for r in self.q(sql, args):
            ev = EventEnvelope.model_validate_json(r["doc"])
            ev.seq = r["seq"]
            out.append(ev)
        return out

    def last_events(self, tenant_id: str, limit: int = 100) -> list[EventEnvelope]:
        rows = self.q("SELECT seq, doc FROM events WHERE (tenant_id=? OR tenant_id='*') AND (run_id IS NULL OR substr(run_id, 1, 4) <> 'run_') "
                      "ORDER BY seq DESC LIMIT ?", (tenant_id, limit))
        out = []
        for r in reversed(rows):
            ev = EventEnvelope.model_validate_json(r["doc"])
            ev.seq = r["seq"]
            out.append(ev)
        return out

    # -- payments + ledger -------------------------------------------------------
    def insert_payment(self, p: PaymentIntent) -> None:
        self.x(
            "INSERT INTO payments (payment_id, tenant_id, case_id, run_id, amount_millimes, currency, method, status, "
            "reason, idempotency_key, created_at, updated_at, doc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.payment_id, p.tenant_id, p.case_id, p.run_id, p.amount_millimes, p.currency, p.method, p.status.value,
             p.reason, p.idempotency_key, _iso(p.created_at), _iso(p.updated_at), p.model_dump_json()),
        )

    def update_payment(self, p: PaymentIntent) -> None:
        self.x("UPDATE payments SET status=?, reason=?, updated_at=?, doc=? WHERE payment_id=?",
               (p.status.value, p.reason, _iso(p.updated_at), p.model_dump_json(), p.payment_id))

    def get_payment(self, payment_id: str) -> PaymentIntent | None:
        rows = self.q("SELECT doc FROM payments WHERE payment_id=?", (payment_id,))
        return PaymentIntent.model_validate_json(rows[0]["doc"]) if rows else None

    def payment_by_idem(self, key: str) -> PaymentIntent | None:
        rows = self.q("SELECT doc FROM payments WHERE idempotency_key=?", (key,))
        return PaymentIntent.model_validate_json(rows[0]["doc"]) if rows else None

    def list_payments(self, tenant_id: str, run_id: str | None = None) -> list[PaymentIntent]:
        if run_id is None:
            rows = self.q("SELECT doc FROM payments WHERE tenant_id=? AND run_id IS NULL ORDER BY created_at", (tenant_id,))
        else:
            rows = self.q("SELECT doc FROM payments WHERE tenant_id=? AND run_id=? ORDER BY created_at", (tenant_id, run_id))
        return [PaymentIntent.model_validate_json(r["doc"]) for r in rows]

    def mark_jti_used(self, jti: str, payment_id: str) -> bool:
        try:
            self.x("INSERT INTO used_authorizations (jti, payment_id, used_at) VALUES (?,?,?)", (jti, payment_id, time.time()))
            return True
        except sqlite3.IntegrityError:
            return False

    # -- decisions -------------------------------------------------------------------
    def save_decision(self, d: ToolDecision, *, run_id: str | None, customer_ref: str | None,
                      idem_key: str | None, method: str | None) -> None:
        self.x(
            "INSERT OR REPLACE INTO decisions (decision_id, tenant_id, case_id, run_id, customer_ref, agent_id, action, "
            "decision, idem_key, method, risk_score, ts_epoch, doc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d.decision_id, d.tenant_id, d.case_id, run_id, customer_ref, d.agent_id, d.action, d.decision.value,
             idem_key, method, d.risk_score, d.ts.timestamp(), json.dumps(d.public())),
        )

    def decisions_by_idem(self, idem_key: str) -> list[dict]:
        rows = self.q("SELECT decision, doc FROM decisions WHERE idem_key=? ORDER BY ts_epoch", (idem_key,))
        return [json.loads(r["doc"]) for r in rows]

    def payment_attempts(self, tenant_id: str, customer_ref: str, since_epoch: float,
                         run_id: str | None = None) -> list[sqlite3.Row]:
        """One row per distinct payment attempt (idempotency key) in the window, inside one scope."""
        return self.q(
            "SELECT idem_key, MIN(method) AS method, MIN(ts_epoch) AS first_ts FROM decisions "
            "WHERE tenant_id=? AND customer_ref=? AND action='pay.create_intent' AND agent_id='sandouk' "
            "AND ts_epoch >= ? AND idem_key IS NOT NULL AND run_id IS ? GROUP BY idem_key ORDER BY first_ts",
            (tenant_id, customer_ref, since_epoch, run_id),
        )

    # -- approvals ---------------------------------------------------------------------
    def save_approval(self, a: Approval) -> None:
        self.x(
            "INSERT INTO approvals (approval_id, tenant_id, case_id, status, created_at, doc) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(approval_id) DO UPDATE SET status=excluded.status, doc=excluded.doc",
            (a.approval_id, a.tenant_id, a.case_id, a.status.value, _iso(a.created_at), a.model_dump_json()),
        )

    def get_approval(self, approval_id: str) -> Approval | None:
        rows = self.q("SELECT doc FROM approvals WHERE approval_id=?", (approval_id,))
        return Approval.model_validate_json(rows[0]["doc"]) if rows else None

    def list_approvals(self, tenant_id: str | None = None, status: ApprovalStatus | None = None) -> list[Approval]:
        sql, args = "SELECT doc FROM approvals WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            args.append(tenant_id)
        if status:
            sql += " AND status=?"
            args.append(status.value)
        sql += " ORDER BY created_at DESC LIMIT 200"
        return [Approval.model_validate_json(r["doc"]) for r in self.q(sql, args)]

    # -- risk signals + quarantined inputs ------------------------------------------------
    def add_signal(self, tenant_id: str, case_id: str, customer_ref: str, sig: RiskSignal) -> None:
        self.x("INSERT INTO risk_signals (tenant_id, case_id, customer_ref, code, weight, ts_epoch, doc) VALUES (?,?,?,?,?,?,?)",
               (tenant_id, case_id, customer_ref, sig.code, sig.weight, sig.ts.timestamp(), sig.model_dump_json()))

    def signals_for_case(self, case_id: str) -> list[RiskSignal]:
        return [RiskSignal.model_validate_json(r["doc"]) for r in self.q("SELECT doc FROM risk_signals WHERE case_id=? ORDER BY id", (case_id,))]

    def quarantine_input(self, qid: str, tenant_id: str, case_id: str, ts: str, text_sha: str, reasons: list[str], text: str) -> None:
        self.x("INSERT INTO quarantine_inputs (qid, tenant_id, case_id, ts, text_sha256, reasons, text) VALUES (?,?,?,?,?,?,?)",
               (qid, tenant_id, case_id, ts, text_sha, json.dumps(reasons), text))

    # -- agent quarantine (kill switch) -----------------------------------------------------
    def quarantine_agent(self, agent_id: str, case_id: str, tenant_id: str, reason: str, requested_by: str, ts: str) -> None:
        self.x("INSERT OR IGNORE INTO agent_quarantine (agent_id, case_id, tenant_id, reason, requested_by, ts) VALUES (?,?,?,?,?,?)",
               (agent_id, case_id, tenant_id, reason, requested_by, ts))

    def active_quarantines(self) -> list[dict]:
        return [dict(r) for r in self.q("SELECT * FROM agent_quarantine WHERE lifted_at IS NULL ORDER BY ts")]

    def is_quarantined(self, agent_id: str, case_id: str) -> bool:
        rows = self.q("SELECT 1 FROM agent_quarantine WHERE agent_id=? AND (case_id=? OR case_id='*') AND lifted_at IS NULL",
                      (agent_id, case_id))
        return bool(rows)

    def lift_quarantine(self, agent_id: str, case_id: str | None, by: str, ts: str) -> int:
        if case_id:
            cur = self.x("UPDATE agent_quarantine SET lifted_by=?, lifted_at=? WHERE agent_id=? AND case_id=? AND lifted_at IS NULL",
                         (by, ts, agent_id, case_id))
        else:
            cur = self.x("UPDATE agent_quarantine SET lifted_by=?, lifted_at=? WHERE agent_id=? AND lifted_at IS NULL", (by, ts, agent_id))
        return cur.rowcount

    # -- scripts + recommendations --------------------------------------------------------------
    def save_script(self, s: ScriptVersion) -> None:
        self.x("INSERT INTO scripts (tenant_id, version, status, doc) VALUES (?,?,?,?) "
               "ON CONFLICT(tenant_id, version) DO UPDATE SET status=excluded.status, doc=excluded.doc",
               (s.tenant_id, s.version, s.status, s.model_dump_json()))

    def get_script(self, tenant_id: str, version: int) -> ScriptVersion | None:
        rows = self.q("SELECT doc FROM scripts WHERE tenant_id=? AND version=?", (tenant_id, version))
        return ScriptVersion.model_validate_json(rows[0]["doc"]) if rows else None

    def active_script(self, tenant_id: str) -> ScriptVersion | None:
        rows = self.q("SELECT doc FROM scripts WHERE tenant_id=? AND status='active' ORDER BY version DESC LIMIT 1", (tenant_id,))
        return ScriptVersion.model_validate_json(rows[0]["doc"]) if rows else None

    def list_scripts(self, tenant_id: str) -> list[ScriptVersion]:
        return [ScriptVersion.model_validate_json(r["doc"]) for r in self.q("SELECT doc FROM scripts WHERE tenant_id=? ORDER BY version", (tenant_id,))]

    def max_script_version(self, tenant_id: str) -> int:
        rows = self.q("SELECT MAX(version) AS v FROM scripts WHERE tenant_id=?", (tenant_id,))
        return int(rows[0]["v"] or 0)

    def save_recommendations(self, recs: list[Recommendation], run_id: str | None, ts: str) -> None:
        with self.tx() as c:
            for r in recs:
                c.execute("INSERT OR REPLACE INTO recommendations (rec_id, tenant_id, run_id, ts, doc) VALUES (?,?,?,?,?)",
                          (r.rec_id, r.tenant_id, run_id, ts, r.model_dump_json()))

    def latest_recommendations(self, tenant_id: str, limit: int = 10) -> list[Recommendation]:
        rows = self.q("SELECT doc FROM recommendations WHERE tenant_id=? ORDER BY ts DESC LIMIT ?", (tenant_id, limit))
        return [Recommendation.model_validate_json(r["doc"]) for r in rows]

    # -- alerts, kpis, runs ----------------------------------------------------------------------
    def insert_alert(self, alert: dict) -> None:
        self.x("INSERT OR IGNORE INTO security_alerts (alert_id, tenant_id, ts, source, type, severity, run_id, doc) VALUES (?,?,?,?,?,?,?,?)",
               (alert["alert_id"], alert["tenant_id"], alert["ts"], alert["source"], alert["type"], alert["severity"],
                alert.get("run_id"), json.dumps(alert, default=str)))

    def list_alerts(self, tenant_id: str | None, limit: int = 100, include_runs: bool = False) -> list[dict]:
        sql, args = "SELECT doc FROM security_alerts WHERE 1=1", []
        if tenant_id:
            sql += " AND (tenant_id=? OR tenant_id='*')"
            args.append(tenant_id)
        if not include_runs:
            sql += " AND (run_id IS NULL OR substr(run_id, 1, 4) <> 'run_')"
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return [json.loads(r["doc"]) for r in self.q(sql, args)]

    def save_kpi_snapshot(self, snap_id: str, tenant_id: str, scope: str, ts: str, doc: str) -> None:
        self.x("INSERT OR REPLACE INTO kpi_snapshots (snap_id, tenant_id, scope, ts, doc) VALUES (?,?,?,?,?)",
               (snap_id, tenant_id, scope, ts, doc))

    def save_run(self, run: dict) -> None:
        self.x("INSERT OR REPLACE INTO runs (run_id, tenant_id, ts, doc) VALUES (?,?,?,?)",
               (run["run_id"], run["tenant_id"], run["started_at"], json.dumps(run, default=str)))

    def get_run(self, run_id: str) -> dict | None:
        rows = self.q("SELECT doc FROM runs WHERE run_id=?", (run_id,))
        return json.loads(rows[0]["doc"]) if rows else None

    def list_runs(self, tenant_id: str) -> list[dict]:
        return [json.loads(r["doc"]) for r in self.q("SELECT doc FROM runs WHERE tenant_id=? ORDER BY ts", (tenant_id,))]
