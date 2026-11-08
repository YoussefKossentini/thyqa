"""Sandouk, the Payment agent (code, no LLM). It asks Bouab, then calls Sandouk Pay
with Bouab's signed authorization. It never computes amounts and never approves itself."""
from __future__ import annotations

from ..schemas import ActionRequest, CaseFile, PaymentIntent, RetryOption, RetryPlan, sha256_hex
from ..tenants import TenantPack


def payment_ids(case: CaseFile) -> tuple[str, str]:
    """Deterministic per attempt: a double submit reuses the key, a retry after a decline gets a new one."""
    if case.offer is None:
        raise ValueError("no offer on this case")
    seed = f"{case.case_id}:{case.offer.offer_hash}:{case.payment_attempt}"
    return f"pay_{sha256_hex('pid:' + seed)[:16]}", sha256_hex("idem:" + seed)[:32]


def build_request(case: CaseFile, correlation_id: str, approval_id: str | None = None,
                  requested_by: str | None = None) -> ActionRequest:
    if case.offer is None:
        raise ValueError("no offer on this case")
    payment_id, idem = payment_ids(case)
    return ActionRequest(
        agent_id="sandouk", action="pay.create_intent", tenant_id=case.tenant_id, case_id=case.case_id,
        payment_id=payment_id, amount_millimes=case.offer.due_now_millimes, currency=case.offer.currency,
        customer_confirmation=case.confirmed_offer_hash == case.offer.offer_hash, idempotency_key=idem,
        approval_id=approval_id, correlation_id=correlation_id,
        params={"method": case.payment_method, **({"requested_by": requested_by} if requested_by else {})},
    )


def retry_plan(p: PaymentIntent, case: CaseFile, tenant: TenantPack) -> RetryPlan:
    options: list[RetryOption] = []
    offer = case.offer
    can_split = bool(offer and offer.installments == 1 and tenant.installment_plans(offer.product_id)
                     and "full_payment_only" not in case.restrictions)
    if p.reason == "insufficient_funds":
        if can_split:
            options.append(RetryOption.SWITCH_TO_INSTALLMENTS)
        options += [RetryOption.SWITCH_TO_BANK_TRANSFER, RetryOption.RETRY_SAME]
    elif p.reason == "suspected_fraud":
        options = [RetryOption.NO_RETRY_ESCALATE]
    elif p.reason == "processor_timeout":
        options = [RetryOption.WAIT_AND_REFRESH]
    else:
        options = [RetryOption.RETRY_SAME, RetryOption.SWITCH_TO_BANK_TRANSFER]
    return RetryPlan(payment_id=p.payment_id, reason=p.reason or "declined", options=options)
