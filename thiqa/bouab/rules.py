"""Deterministic payment rules and risk score. No LLM anywhere in this file."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, tzinfo

from ..db import Repo
from ..money import fmt_tnd
from ..schemas import ActionRequest, CaseFile, Decision, Reason, RiskSignal, canonical_json, sha256_hex
from ..tenants import TenantPack

WEIGHTS = {
    "injection_attempt": 25,
    "unusual_amount": 15,
    "velocity": 10,
    "method_mismatch": 10,
    "failed_step_up": 20,
    "time_anomaly": 5,
    "processor_fraud_flag": 20,
    "isolation_forest": 10,
}


def request_hash(payment_id: str | None, amount_millimes: int | None, currency: str | None,
                 customer_ref: str, idempotency_key: str | None) -> str:
    """What a human approves. Change any field and the approval no longer applies."""
    return sha256_hex(canonical_json({"payment_id": payment_id, "amount_millimes": amount_millimes,
                                      "currency": currency, "customer": customer_ref,
                                      "idempotency_key": idempotency_key}))


@dataclass
class RuleHit:
    rule_id: str
    outcome: Decision      # BLOCK or REQUIRE_APPROVAL
    code: str
    message: str

    def reason(self) -> Reason:
        return Reason(code=self.code, rule_id=self.rule_id, message=self.message)


def attempts_in_window(repo: Repo, req: ActionRequest, case: CaseFile, tenant: TenantPack) -> tuple[int, set[str]]:
    since = time.time() - tenant.thresholds.velocity_window_seconds
    rows = repo.payment_attempts(tenant.tenant_id, case.customer_ref, since, case.run_id)
    keys = {r["idem_key"] for r in rows}
    methods = {r["method"] for r in rows if r["method"]}
    count = len(keys | ({req.idempotency_key} if req.idempotency_key else set()))
    method = req.params.get("method")
    if method:
        methods.add(str(method))
    return count, methods


def evaluate_payment_rules(req: ActionRequest, case: CaseFile, tenant: TenantPack, repo: Repo,
                           check_velocity: bool = True) -> list[RuleHit]:
    th = tenant.thresholds
    hits: list[RuleHit] = []
    offer = case.offer
    # R01: explicit confirmation bound to this exact offer
    if not req.customer_confirmation or offer is None or case.confirmed_offer_hash != offer.offer_hash:
        hits.append(RuleHit("R01", Decision.BLOCK, "R01_CONFIRMATION_MISSING",
                            "No explicit customer confirmation of this exact offer"))
    # R03: amount must be positive
    if req.amount_millimes is None or req.amount_millimes <= 0:
        hits.append(RuleHit("R03", Decision.BLOCK, "R03_AMOUNT_NOT_POSITIVE", "Amount must be greater than 0"))
    # R05: tenant currency only
    if req.currency != tenant.currency:
        hits.append(RuleHit("R05", Decision.BLOCK, "R05_CURRENCY", f"Currency must be {tenant.currency}"))
    # R06: amount recomputed from the catalog right now, never trusted from the caller
    if offer is not None and req.amount_millimes is not None:
        try:
            _, schedule, _ = tenant.price_for(offer.product_id, offer.plan_id, offer.discount_code)
            expected = schedule[0]
        except ValueError:
            expected = None
        if expected is None or req.amount_millimes != expected:
            shown = fmt_tnd(expected) if expected else "nothing (offer not in catalog)"
            hits.append(RuleHit("R06", Decision.BLOCK, "R06_AMOUNT_MISMATCH",
                                f"Amount {fmt_tnd(req.amount_millimes)} differs from catalog price x plan ({shown})"))
    # R07: velocity hard limit (card testing)
    if check_velocity:
        count, _ = attempts_in_window(repo, req, case, tenant)
        if count > th.velocity_max_attempts:
            hits.append(RuleHit("R07", Decision.BLOCK, "R07_VELOCITY_LIMIT",
                                f"{count} payment attempts in {th.velocity_window_seconds}s (max {th.velocity_max_attempts})"))
    # R02: above the approval threshold, a human decides
    if req.amount_millimes is not None and req.amount_millimes > th.approval_threshold_millimes:
        hits.append(RuleHit("R02", Decision.REQUIRE_APPROVAL, "R02_APPROVAL_THRESHOLD",
                            f"{fmt_tnd(req.amount_millimes)} is above the approval threshold ({fmt_tnd(th.approval_threshold_millimes)})"))
    return hits


def risk_score(req: ActionRequest, case: CaseFile, tenant: TenantPack, repo: Repo, tz: tzinfo,
               time_anomaly_enabled: bool = True, extra: list[RiskSignal] | None = None) -> tuple[int, list[RiskSignal]]:
    """Weighted score 0..100. Every signal is stored and shown, so the score explains itself."""
    th = tenant.thresholds
    signals: list[RiskSignal] = [s for s in repo.signals_for_case(case.case_id)
                                 if s.code in ("injection_attempt", "failed_step_up", "processor_fraud_flag")]
    if req.amount_millimes and req.amount_millimes > th.approval_threshold_millimes:
        signals.append(RiskSignal(code="unusual_amount", weight=WEIGHTS["unusual_amount"],
                                  detail="amount above the tenant approval threshold"))
    count, methods = attempts_in_window(repo, req, case, tenant)
    extra_attempts = max(0, count - th.velocity_free_attempts)
    if extra_attempts:
        signals.append(RiskSignal(code="velocity", weight=min(30, WEIGHTS["velocity"] * extra_attempts),
                                  detail=f"{count} attempts in {th.velocity_window_seconds}s"))
    if len(methods) >= 2:
        signals.append(RiskSignal(code="method_mismatch", weight=WEIGHTS["method_mismatch"],
                                  detail=f"{len(methods)} different payment methods in the window"))
    if time_anomaly_enabled and len(th.time_anomaly_hours) == 2:
        start, end = th.time_anomaly_hours
        hour = datetime.now(tz).hour
        if start <= hour < end:
            signals.append(RiskSignal(code="time_anomaly", weight=WEIGHTS["time_anomaly"],
                                      detail=f"local hour {hour}h is in the unusual window"))
    signals.extend(extra or [])
    return min(100, sum(s.weight for s in signals)), signals
