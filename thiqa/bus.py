"""In-process event bus. One envelope feeds the Majlis feed, the audit chain,
security.jsonl (for Wazuh), the alert list and replay.

Production path: NATS / Kafka behind the same publish() call.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

from .audit import AuditChain
from .db import Repo
from .schemas import AIMode, Decision, EventEnvelope, EventType, Severity, new_id, sha256_hex
from .seclog import SecurityLog

ET = EventType

# Not audited: chatty or text-carrying events (the transcript lives in the Case File)
NOT_AUDITED = {ET.TURN_CLIENT, ET.TURN_SAHBI, ET.FAHEM_ANALYSIS, ET.KPI_UPDATED, ET.SIEM_STATUS, ET.RUN_STARTED}
# Batch runs (Zbayen) only broadcast these, so 50 simulated clients do not flood the feed
RUN_BROADCAST = {ET.RUN_STARTED, ET.RUN_FINISHED, ET.KPI_UPDATED}

SEVERITY_ORDER = {s: i for i, s in enumerate([Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL])}


def security_line(ev: EventEnvelope) -> dict[str, Any] | None:
    """Map an event to the fixed security.jsonl fields, or None if not a security event."""
    p = ev.payload
    reasons = p.get("reasons") or []
    first_reason = reasons[0]["code"] if reasons and isinstance(reasons[0], dict) else p.get("reason")
    base = {"agent_id": p.get("agent_id") or ev.source, "tool": p.get("action") or p.get("tool"),
            "decision": ev.decision.value if ev.decision else None, "reason": first_reason, "severity": ev.severity.value}
    if ev.type == ET.TOOL_DENIED:
        return {**base, "event_type": "TOOL_DENIED"}
    if ev.type == ET.INPUT_FLAGGED:
        return {**base, "agent_id": "client", "tool": "input_guard", "event_type": "prompt_injection_detected",
                "reason": (p.get("reasons") or ["rule"])[0]}
    if ev.type == ET.OUTPUT_REWRITTEN:
        return {**base, "agent_id": "sahbi", "tool": "output_guard", "event_type": "output_guard_rewrite",
                "reason": (p.get("reasons") or ["rule"])[0]}
    if ev.type == ET.BOUAB_DECISION and ev.decision == Decision.BLOCK:
        codes = [r.get("code", "") for r in reasons if isinstance(r, dict)]
        kind = "velocity_block" if any(c.startswith("R07") for c in codes) else "payment_blocked"
        return {**base, "event_type": kind}
    if ev.type == ET.PAYMENT_ENGINE_REJECTED:
        return {**base, "tool": "sandouk_pay", "event_type": "payment_engine_rejected"}
    if ev.type == ET.APPROVAL_REFUSED:
        kind = {"self_approval": "approval_self_attempt", "replay": "approval_replay",
                "hash_mismatch": "approval_hash_mismatch"}.get(p.get("refusal", ""), "approval_refused")
        return {**base, "agent_id": p.get("approver_id") or ev.source, "tool": "approval", "event_type": kind}
    if ev.type == ET.AGENT_QUARANTINED:
        return {**base, "agent_id": p.get("agent_id"), "tool": "kill_switch", "event_type": "agent_quarantined"}
    if ev.type == ET.AUDIT_VERIFIED and not p.get("ok", True):
        return {**base, "agent_id": "bouab", "tool": "audit", "event_type": "audit_chain_invalid"}
    if ev.type == ET.POLICY_TAMPERED:
        return {**base, "agent_id": "bouab", "tool": "policy", "event_type": "policy_file_changed"}
    return None


class EventBus:
    def __init__(self, repo: Repo, audit: AuditChain, seclog: SecurityLog):
        self.repo = repo
        self.audit = audit
        self.seclog = seclog
        self._subs: list[tuple[asyncio.Queue, str | None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, tenant_id: str | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        with self._lock:
            self._subs.append((q, tenant_id))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = [(s, t) for s, t in self._subs if s is not q]

    # ------------------------------------------------------------------------------
    def emit(self, type: EventType, *, tenant_id: str, source: str, summary: str,
             case_id: str | None = None, run_id: str | None = None, correlation_id: str | None = None,
             target: str | None = None, decision: Decision | None = None, severity: Severity = Severity.INFO,
             mode: AIMode | None = None, payload: dict[str, Any] | None = None) -> EventEnvelope:
        ev = EventEnvelope(
            tenant_id=tenant_id, case_id=case_id, run_id=run_id, correlation_id=correlation_id or new_id("cor"),
            type=type, source=source, target=target, decision=decision, severity=severity, mode=mode,
            summary=summary[:300], payload=payload or {},
        )
        return self.publish(ev)

    def publish(self, ev: EventEnvelope) -> EventEnvelope:
        ev.seq = self.repo.insert_event(ev)
        if ev.type not in NOT_AUDITED:
            self.audit.append(tenant_id=ev.tenant_id, actor=ev.source, action=ev.type.value,
                              decision=ev.decision.value if ev.decision else None, data=self._audit_data(ev))
        is_batch = bool(ev.run_id and ev.run_id.startswith("run_"))
        line = security_line(ev)
        if line and not is_batch:
            self.seclog.write(tenant_id=ev.tenant_id, correlation_id=ev.correlation_id, **line)
            if SEVERITY_ORDER[ev.severity] >= SEVERITY_ORDER[Severity.MEDIUM]:
                self.repo.insert_alert({
                    "alert_id": ev.event_id, "tenant_id": ev.tenant_id, "ts": ev.ts.isoformat(), "source": "bouab",
                    "type": line["event_type"], "severity": ev.severity.value, "case_id": ev.case_id,
                    "summary": ev.summary, "run_id": ev.run_id,
                })
        if not is_batch or ev.type in RUN_BROADCAST:
            self._fanout(ev)
        return ev

    @staticmethod
    def _audit_data(ev: EventEnvelope) -> dict[str, Any]:
        data = {k: v for k, v in ev.payload.items() if k not in ("text", "reply", "authorization")}
        if "text" in ev.payload:  # keep proof that text existed, never the text itself
            data["text_sha256"] = sha256_hex(str(ev.payload["text"]))
        data.update({"event_id": ev.event_id, "case_id": ev.case_id, "run_id": ev.run_id, "correlation_id": ev.correlation_id})
        return data

    def _fanout(self, ev: EventEnvelope) -> None:
        if not self._subs:
            return
        message = ev.model_dump(mode="json")

        def deliver() -> None:
            with self._lock:
                subs = list(self._subs)
            for q, tenant in subs:
                if tenant and tenant != ev.tenant_id and ev.tenant_id != "*":
                    continue
                if q.full():
                    try:
                        q.get_nowait()  # drop the oldest rather than block the money path
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(message)

        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is None or running is loop:
            deliver()
        else:
            loop.call_soon_threadsafe(deliver)
