"""Bouab, the independent security controller.

Pipeline for every agent tool call:
  Interceptor -> Permission manager (policy.yaml) -> Rule engine -> Risk detector
  -> Decision manager -> Approval manager -> Signed authorization.
Bouab is code, not a prompt. Even a fully hijacked agent cannot move money:
the decision and the authorization live outside every LLM.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..bus import EventBus
from ..db import Repo
from ..money import fmt_tnd
from ..schemas import (
    ActionRequest,
    CaseFile,
    Decision,
    EventType,
    Reason,
    RiskSignal,
    ScriptVersion,
    Severity,
    ToolDecision,
    new_id,
    sha256_hex,
    utcnow,
)
from ..settings import Settings
from ..tenants import TenantRegistry
from ..llm import mock_forced
from .anomaly import FraudModel
from .approvals import ApprovalManager
from .authz import Authorizer
from .input_guard import GuardVerdict, InputGuard
from .killswitch import KillSwitch
from .output_guard import OutputGuard, OutputVerdict
from .policy import Policy
from .rules import WEIGHTS, attempts_in_window, evaluate_payment_rules, request_hash, risk_score
from .script_guard import check_script

ET = EventType


class Bouab:
    def __init__(self, *, repo: Repo, bus: EventBus, tenants: TenantRegistry, policy: Policy, authorizer: Authorizer,
                 approvals: ApprovalManager, killswitch: KillSwitch, input_guard: InputGuard,
                 output_guard: OutputGuard, settings: Settings, fraud_model: FraudModel | None = None):
        self.repo = repo
        self.bus = bus
        self.tenants = tenants
        self.policy = policy
        self.authorizer = authorizer
        self.approvals = approvals
        self.killswitch = killswitch
        self.input_guard = input_guard
        self.output_guard = output_guard
        self.settings = settings
        self.fraud_model = fraud_model
        self._protected = self._protected_files()
        self._tamper_seen: set[tuple[str, str | None]] = set()

    # ===================================================================== tool gateway
    def call_tool(self, req: ActionRequest) -> ToolDecision:
        corr = req.correlation_id or new_id("cor")
        agent, action = req.agent_id, req.action

        def deny(code: str, rule_id: str, message: str, severity: Severity = Severity.HIGH,
                 event: EventType = ET.BOUAB_DECISION) -> ToolDecision:
            d = ToolDecision(decision_id=new_id("dec"), decision=Decision.BLOCK, agent_id=agent, action=action,
                             tenant_id=req.tenant_id, case_id=req.case_id,
                             reasons=[Reason(code=code, rule_id=rule_id, message=message)])
            self._emit_decision(d, corr, severity, event=event, run_id=case.run_id if case else None)
            return d

        # 1. Interceptor
        case = None
        if not self.tenants.has(req.tenant_id):
            return deny("I01_UNKNOWN_TENANT", "I01", "Unknown tenant")
        case = self.repo.get_case(req.case_id)
        if case is None or case.tenant_id != req.tenant_id:
            case = None
            return deny("I02_TENANT_ISOLATION", "I02", "Case does not belong to this tenant")
        if self.killswitch.record_call(agent, case.case_id):
            self.quarantine_agent(agent, case, "abnormal burst of tool calls")
        if self.killswitch.is_quarantined(agent, case.case_id):
            return deny("K01_AGENT_QUARANTINED", "K01", f"{agent} is quarantined on this case; a human must release it")

        # 2. Permission manager
        if not self.policy.allowed(agent, action):
            d = deny("P01_TOOL_DENIED", "P01", f"{agent} is not allowed to call {action}", event=ET.TOOL_DENIED)
            if self.killswitch.record_denied(agent, case.case_id):
                self.quarantine_agent(agent, case, f"{self.killswitch.denied_calls} denied calls in {self.killswitch.window_s}s")
            return d

        if action not in self.policy.sensitive:
            return ToolDecision(decision_id=new_id("dec"), decision=Decision.ALLOW, agent_id=agent, action=action,
                                tenant_id=req.tenant_id, case_id=req.case_id)
        if action == "pay.create_intent":
            return self._payment(req, case, corr)
        return deny("I03_UNSUPPORTED", "I03", f"No rule set for sensitive tool {action}")

    # ===================================================================== payments
    def _payment(self, req: ActionRequest, case: CaseFile, corr: str) -> ToolDecision:
        tenant = self.tenants.get(case.tenant_id)
        th = tenant.thresholds
        rh = request_hash(req.payment_id, req.amount_millimes, req.currency, case.customer_ref, req.idempotency_key)
        d = ToolDecision(decision_id=new_id("dec"), decision=Decision.BLOCK, agent_id=req.agent_id, action=req.action,
                         tenant_id=case.tenant_id, case_id=case.case_id, request_hash=rh)
        severity = Severity.HIGH

        if not req.payment_id or not req.idempotency_key:
            d.reasons = [Reason(code="I04_MISSING_IDS", rule_id="I04", message="payment_id and idempotency_key are required")]
            return self._finish(d, req, case, corr, severity)

        prior = self.repo.decisions_by_idem(req.idempotency_key)
        existing = self.repo.payment_by_idem(req.idempotency_key)

        if req.approval_id:  # ---- resume after a human approval
            res = self.approvals.consume(req.approval_id, rh, tenant.tenant_id)
            if not res.ok:
                self.bus.emit(ET.APPROVAL_REFUSED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                              correlation_id=corr, source="bouab", target="sandouk", decision=Decision.BLOCK,
                              severity=Severity.HIGH, summary=f"Fouchika refused approval {req.approval_id}: {res.message}",
                              payload={"approval_id": req.approval_id, "refusal": res.refusal, "agent_id": req.agent_id,
                                       "reasons": [{"code": f"A_{(res.refusal or 'refused').upper()}"}]})
                d.reasons = [Reason(code=f"A_{(res.refusal or 'refused').upper()}", rule_id="A", message=res.message)]
                d.approval_id = req.approval_id
                return self._finish(d, req, case, corr, severity)
            hits = evaluate_payment_rules(req, case, tenant, self.repo, check_velocity=False)
            hard = [h for h in hits if h.outcome == Decision.BLOCK]
            score, signals = risk_score(req, case, tenant, self.repo, self.settings.tz, self.settings.time_anomaly_enabled and not mock_forced(),
                                        extra=self.ml_signal(req, case))
            d.risk_score, d.signals, d.approval_id = score, signals, req.approval_id
            approvers = ", ".join(a for a in (res.approval.approvals if res.approval else []))
            if hard:
                d.reasons = [h.reason() for h in hard]
            elif score > th.risk_block_above:
                d.reasons = [Reason(code="RISK_HIGH", rule_id="RISK", message=f"risk {score} > {th.risk_block_above} after approval")]
            else:
                d.decision = Decision.ALLOW
                d.reasons = [Reason(code="A_APPROVED", rule_id="A", message=f"approved by {approvers}")]
                severity = Severity.INFO
            return self._finish(d, req, case, corr, severity)

        # ---- fresh request: idempotency first (R04)
        if existing or any(p["decision"] == Decision.ALLOW for p in prior):
            d.reasons = [Reason(code="R04_DUPLICATE", rule_id="R04", message="Duplicate idempotency key: the first request already ran")]
            d.existing_payment_id = existing.payment_id if existing else None
            return self._finish(d, req, case, corr, Severity.LOW)
        if prior:
            last = prior[-1]
            d.reasons = [Reason(code="R04_DUPLICATE", rule_id="R04",
                                message=f"Duplicate idempotency key: original request is {last['decision']}")]
            d.approval_id = last.get("approval_id")
            return self._finish(d, req, case, corr, Severity.LOW)

        hits = evaluate_payment_rules(req, case, tenant, self.repo)
        score, signals = risk_score(req, case, tenant, self.repo, self.settings.tz, self.settings.time_anomaly_enabled and not mock_forced(),
                                    extra=self.ml_signal(req, case))
        d.risk_score, d.signals = score, signals
        hard = [h for h in hits if h.outcome == Decision.BLOCK]
        needs_human = [h for h in hits if h.outcome == Decision.REQUIRE_APPROVAL]
        d.reasons = [h.reason() for h in hits]

        if hard:
            d.decision = Decision.BLOCK
        elif score > th.risk_block_above:
            d.decision = Decision.BLOCK
            d.reasons.append(Reason(code="RISK_HIGH", rule_id="RISK", message=f"risk {score} > {th.risk_block_above}"))
        elif needs_human:
            d.decision = Decision.REQUIRE_APPROVAL
        elif score >= th.risk_allow_below:
            d.restrictions = ["full_payment_only"]
            if case.offer and case.offer.installments > 1:
                d.decision = Decision.REQUIRE_APPROVAL
                d.reasons.append(Reason(code="RISK_MEDIUM_INSTALLMENTS", rule_id="RISK",
                                        message=f"risk {score}: installments need a human, or switch to full payment"))
            else:
                d.decision = Decision.ALLOW
                d.reasons.append(Reason(code="RISK_MEDIUM_FULL_ONLY", rule_id="RISK",
                                        message=f"risk {score}: full payment only on this case"))
        else:
            d.decision = Decision.ALLOW

        if d.decision == Decision.REQUIRE_APPROVAL:
            severity = Severity.MEDIUM
            approval = self.approvals.create(
                tenant=tenant, case_id=case.case_id, payment_id=req.payment_id, decision_id=d.decision_id,
                request_hash=rh, amount_millimes=req.amount_millimes or 0, currency=req.currency or "",
                customer_ref=case.customer_ref, product_name=case.offer.product_name if case.offer else "?",
                requested_by=str(req.params.get("requested_by") or f"agent:{req.agent_id}"),
                reasons=d.reasons, risk_score=score)
            d.approval_id = approval.approval_id
            self.bus.emit(ET.APPROVAL_REQUESTED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="bouab", target="human", decision=Decision.REQUIRE_APPROVAL,
                          severity=Severity.MEDIUM,
                          summary=f"Approval needed: {fmt_tnd(approval.amount_millimes)} for {approval.product_name} "
                                  f"({approval.required_approvals} approver{'s' if approval.required_approvals > 1 else ''})",
                          payload=approval.model_dump(mode="json"))
        elif d.decision == Decision.ALLOW:
            severity = Severity.INFO
        return self._finish(d, req, case, corr, severity)

    def ml_features(self, req: ActionRequest, case: CaseFile) -> dict[str, float]:
        tenant = self.tenants.get(case.tenant_id)
        count, methods = attempts_in_window(self.repo, req, case, tenant)
        hour = datetime.now(self.settings.tz).hour
        simulated = mock_forced()
        client_turns = sum(1 for t in case.turns if t.role == "client" and not t.withheld)
        minutes = 0.5 * client_turns if simulated else max(0.0, (utcnow() - case.created_at).total_seconds() / 60)
        return {
            "amount_ratio": round((req.amount_millimes or 0) / FraudModel.reference_price(tenant), 3),
            "attempts_window": count,
            "distinct_methods": max(1, len(methods)),
            "night": int(hour < 6) if self.settings.time_anomaly_enabled and not simulated else 0,
            "injections": sum(1 for s in self.repo.signals_for_case(case.case_id) if s.code == "injection_attempt"),
            "client_turns": client_turns,
            "minutes_open": round(minutes, 2),
        }

    def ml_signal(self, req: ActionRequest, case: CaseFile) -> list[RiskSignal]:
        if self.fraud_model is None or not self.fraud_model.enabled:
            return []
        res = self.fraud_model.score(self.tenants.get(case.tenant_id), self.ml_features(req, case))
        if res is None or not res.anomaly:
            return []
        return [RiskSignal(code="isolation_forest", weight=WEIGHTS["isolation_forest"], detail=res.detail())]

    def _finish(self, d: ToolDecision, req: ActionRequest, case: CaseFile, corr: str, severity: Severity) -> ToolDecision:
        if d.decision == Decision.ALLOW:
            d.authorization = self.authorizer.issue(payment_id=req.payment_id or "", tenant_id=case.tenant_id,
                                                    amount_millimes=req.amount_millimes or 0,
                                                    currency=req.currency or "", request_hash=d.request_hash or "")
        self.repo.save_decision(d, run_id=case.run_id, customer_ref=case.customer_ref,
                                idem_key=req.idempotency_key, method=str(req.params.get("method") or "") or None)
        self._emit_decision(d, corr, severity, run_id=case.run_id, amount=req.amount_millimes)
        if d.decision == Decision.ALLOW:
            self.bus.emit(ET.AUTHORIZATION_ISSUED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="bouab", target="sandouk",
                          summary=f"Fouchika signed an authorization for {fmt_tnd(req.amount_millimes or 0)} (single use, 120 s)",
                          payload={"decision_id": d.decision_id, "payment_id": req.payment_id,
                                   "amount_millimes": req.amount_millimes, "request_hash": d.request_hash})
        return d

    def _emit_decision(self, d: ToolDecision, corr: str, severity: Severity, event: EventType = ET.BOUAB_DECISION,
                       run_id: str | None = None, amount: int | None = None) -> None:
        what = f" for {fmt_tnd(amount)}" if amount else ""
        why = "; ".join(r.code for r in d.reasons) or "all checks passed"
        if event == ET.TOOL_DENIED:
            summary = f"Fouchika: TOOL_DENIED, {d.agent_id} tried {d.action}"
        else:
            summary = f"Fouchika: {d.decision.value}{what} ({why}), risk {d.risk_score}"
        self.bus.emit(event, tenant_id=d.tenant_id, case_id=d.case_id, run_id=run_id, correlation_id=corr,
                      source="bouab", target=d.agent_id, decision=d.decision, severity=severity, summary=summary,
                      payload={**d.public(), "amount_millimes": amount, "explanation": self.explain(d)})

    # ===================================================================== guards
    def screen_input(self, case: CaseFile, text: str, corr: str) -> GuardVerdict:
        v = self.input_guard.check(text)
        if v.flagged:
            qid = new_id("q")
            self.repo.quarantine_input(qid, case.tenant_id, case.case_id, case.updated_at.isoformat(),
                                       sha256_hex(text), v.reasons, text)
            self.record_signal(case, "injection_attempt", f"input guard: {', '.join(v.reasons[:3])}")
            self.bus.emit(ET.INPUT_FLAGGED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="bouab", target="client", decision=Decision.BLOCK,
                          severity=Severity.HIGH,
                          summary=f"Fouchika BLOCKED a message before Sboui ({', '.join(v.reasons[:3])})",
                          payload={"reasons": v.reasons, "qid": qid, "text": text[:200], "lang": v.lang.value,
                                   "case_risk": self.case_risk(case)})
        return v

    def screen_output(self, case: CaseFile, text: str, corr: str, lang) -> OutputVerdict:
        tenant = self.tenants.get(case.tenant_id)
        v = self.output_guard.check(text, tenant, case.offer, lang)
        if not v.ok:
            self.bus.emit(ET.OUTPUT_REWRITTEN, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="bouab", target="sahbi", decision=Decision.BLOCK,
                          severity=Severity.CRITICAL if v.leak else Severity.MEDIUM,
                          summary=f"Fouchika replaced Sboui's reply before the client saw it ({', '.join(v.reasons[:2])})",
                          payload={"reasons": v.reasons, "original": "[withheld: leak]" if v.leak else text[:240],
                                   "replacement": v.text})
        return v

    def record_signal(self, case: CaseFile, code: str, detail: str) -> RiskSignal:
        sig = RiskSignal(code=code, weight=WEIGHTS[code], detail=detail)  # type: ignore[arg-type]
        self.repo.add_signal(case.tenant_id, case.case_id, case.customer_ref, sig)
        return sig

    def case_risk(self, case: CaseFile) -> int:
        return min(100, sum(s.weight for s in self.repo.signals_for_case(case.case_id)))

    def should_block_case(self, case: CaseFile) -> bool:
        return self.case_risk(case) > self.tenants.get(case.tenant_id).thresholds.risk_block_above

    # ===================================================================== kill switch
    def quarantine_agent(self, agent_id: str, case: CaseFile | None, reason: str, requested_by: str = "bouab",
                         case_id: str | None = None, tenant_id: str | None = None) -> None:
        cid = case.case_id if case else (case_id or "*")
        tid = case.tenant_id if case else (tenant_id or "*")
        self.killswitch.quarantine(agent_id, cid, tid, reason, requested_by)
        self.bus.emit(ET.AGENT_QUARANTINED, tenant_id=tid, case_id=None if cid == "*" else cid,
                      run_id=case.run_id if case else None, source="bouab", target=agent_id,
                      decision=Decision.BLOCK, severity=Severity.CRITICAL,
                      summary=f"Fouchika quarantined {agent_id}{'' if cid == '*' else ' on case ' + cid[-6:]}: {reason}",
                      payload={"agent_id": agent_id, "case_id": cid, "reason": reason, "requested_by": requested_by})

    def release_agent(self, agent_id: str, case_id: str | None, by_human: str, tenant_id: str) -> int:
        n = self.killswitch.lift(agent_id, case_id, by_human)
        self.bus.emit(ET.AGENT_RELEASED, tenant_id=tenant_id, case_id=case_id, source=f"human:{by_human}",
                      target=agent_id, summary=f"{by_human} released {agent_id} ({n} quarantine{'s' if n != 1 else ''})",
                      payload={"agent_id": agent_id, "case_id": case_id, "lifted": n})
        return n

    # ===================================================================== scripts
    def check_script(self, proposed: ScriptVersion, current: ScriptVersion, next_version: int) -> tuple[list[Reason], dict]:
        tenant = self.tenants.get(proposed.tenant_id)
        reasons, diff = check_script(proposed, current, tenant, next_version)
        self.bus.emit(ET.SCRIPT_CHECKED, tenant_id=proposed.tenant_id, source="bouab", target="le_renard",
                      decision=Decision.BLOCK if reasons else Decision.ALLOW,
                      severity=Severity.MEDIUM if reasons else Severity.INFO,
                      summary=(f"Fouchika rejected script v{proposed.version}: {', '.join(r.code for r in reasons)}" if reasons
                               else f"Fouchika checked script v{proposed.version}: only editable fields changed, ready for a human"),
                      payload={"version": proposed.version, "reasons": [r.model_dump() for r in reasons], "diff": diff})
        return reasons, diff

    # ===================================================================== explain + audit + tamper
    @staticmethod
    def explain(d: ToolDecision) -> str:
        parts = [f"{d.decision.value}"]
        if d.reasons:
            parts.append("because " + "; ".join(r.message for r in d.reasons))
        if d.signals:
            parts.append("risk " + str(d.risk_score) + " = " + " + ".join(f"{s.code} {s.weight}" for s in d.signals))
        if d.decision == Decision.BLOCK:
            parts.append("A BLOCK cannot be approved.")
        return ". ".join(parts)

    def verify_audit(self, by: str, tenant_id: str) -> dict:
        result = self.bus.audit.verify()
        self.bus.emit(ET.AUDIT_VERIFIED, tenant_id=tenant_id, source="bouab", target=by,
                      decision=Decision.ALLOW if result["ok"] else Decision.BLOCK,
                      severity=Severity.INFO if result["ok"] else Severity.CRITICAL,
                      summary=(f"Audit chain verified: {result['checked']} rows intact" if result["ok"]
                               else f"Audit chain BROKEN at row {result.get('first_bad_seq')}: {result.get('reason')}"),
                      payload=result)
        return result

    def _protected_files(self) -> dict[Path, str | None]:
        files: dict[Path, str | None] = {self.policy.path: self.policy.sha256}
        files.update(self.tenants.files())
        env = self.settings.root / ".env"
        files[env] = sha256_hex(env.read_bytes()) if env.exists() else None
        return files

    def check_protected_files(self) -> list[str]:
        """Detection in the app (Wazuh FIM does the same outside). The loaded policy never changes at runtime."""
        changed = []
        for path, loaded in self._protected.items():
            try:
                now = sha256_hex(path.read_bytes()) if path.exists() else None
            except OSError:
                now = None
            if now != loaded and (str(path), now) not in self._tamper_seen:
                self._tamper_seen.add((str(path), now))
                changed.append(path.name)
                self.bus.emit(ET.POLICY_TAMPERED, tenant_id="*", source="bouab", target="human",
                              decision=Decision.BLOCK, severity=Severity.CRITICAL,
                              summary=f"{path.name} changed on disk. Fouchika keeps the policy loaded at startup "
                                      f"(sha {loaded[:10] if loaded else 'none'}...) and ignores the new file",
                              payload={"file": path.name, "loaded_sha256": loaded, "disk_sha256": now,
                                       "reason": "PROTECTED_FILE_CHANGED"})
        return changed
