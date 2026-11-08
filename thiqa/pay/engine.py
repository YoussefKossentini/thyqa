"""Sandouk Pay: the mock payment gateway (SIMULATED, no real money).

It trusts nobody. Before executing it verifies Bouab's signed authorization
itself: no token, a forged one, another amount or payment, an expired or a
reused token are all rejected. Sandbox tokens give deterministic results.
Production path: Flouci / Konnect adapters behind the same create_intent().
"""
from __future__ import annotations

from ..bus import EventBus
from ..db import Repo
from ..money import fmt_tnd
from ..schemas import Decision, EventType, PaymentIntent, PaymentStatus, SandboxToken, Severity, utcnow
from ..bouab.authz import AuthzError, verify_authorization
from .ledger import Ledger

TOKENS: dict[str, tuple[PaymentStatus, str | None]] = {
    SandboxToken.OK: (PaymentStatus.SUCCEEDED, None),
    SandboxToken.INSUFFICIENT: (PaymentStatus.DECLINED, "insufficient_funds"),
    SandboxToken.TIMEOUT: (PaymentStatus.PENDING, "processor_timeout"),
    SandboxToken.FRAUD: (PaymentStatus.DECLINED, "suspected_fraud"),
    SandboxToken.BANK_TRANSFER: (PaymentStatus.PENDING, "awaiting_transfer"),
}


class EngineRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SandoukPay:
    def __init__(self, repo: Repo, bus: EventBus, ledger: Ledger, authz_secret: bytes):
        self.repo = repo
        self.bus = bus
        self.ledger = ledger
        self._secret = authz_secret

    def create_intent(self, *, payment_id: str, tenant_id: str, case_id: str, amount_millimes: int, currency: str,
                      method: str, idempotency_key: str, authorization: str | None, caller: str = "sandouk",
                      run_id: str | None = None, correlation_id: str | None = None) -> PaymentIntent:
        try:
            claims = verify_authorization(authorization, self._secret, payment_id=payment_id, tenant_id=tenant_id,
                                          amount_millimes=amount_millimes, currency=currency)
            if not self.repo.mark_jti_used(claims["jti"], payment_id):
                raise AuthzError("AUTHZ_REPLAYED", "authorization already used once")
        except AuthzError as exc:
            self.bus.emit(EventType.PAYMENT_ENGINE_REJECTED, tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                          correlation_id=correlation_id, source="sandouk_pay", target=caller, decision=Decision.BLOCK,
                          severity=Severity.CRITICAL,
                          summary=f"Janet Pay rejected {fmt_tnd(amount_millimes)} from {caller}: {exc.code}",
                          payload={"agent_id": caller, "payment_id": payment_id, "amount_millimes": amount_millimes,
                                   "reason": exc.code, "message": str(exc)})
            raise EngineRejected(exc.code, str(exc)) from exc

        existing = self.repo.payment_by_idem(idempotency_key)
        if existing:  # defense in depth behind R04: never charge twice
            return existing

        status, reason = TOKENS.get(method, (PaymentStatus.DECLINED, "invalid_token"))
        intent = PaymentIntent(payment_id=payment_id, tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                               amount_millimes=amount_millimes, currency=currency, method=method, status=status,
                               reason=reason, idempotency_key=idempotency_key)
        self.repo.insert_payment(intent)
        self.bus.emit(EventType.PAYMENT_CREATED, tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                      correlation_id=correlation_id, source="sandouk", target="sandouk_pay",
                      summary=f"SIMULATED payment {fmt_tnd(amount_millimes)} via {method}: {status.value}"
                              + (f" ({reason})" if reason else ""),
                      severity=Severity.INFO if status != PaymentStatus.DECLINED else Severity.LOW,
                      payload=intent.model_dump(mode="json"))
        if status == PaymentStatus.SUCCEEDED:
            self._post(intent, correlation_id)
        return intent

    def _post(self, intent: PaymentIntent, correlation_id: str | None) -> None:
        entry = self.ledger.post_payment(intent)
        self.bus.emit(EventType.LEDGER_POSTED, tenant_id=intent.tenant_id, case_id=intent.case_id, run_id=intent.run_id,
                      correlation_id=correlation_id, source="sandouk", target="si_hsab",
                      summary=f"Ledger: debit sandbox_cash / credit sales_revenue {fmt_tnd(intent.amount_millimes)}",
                      payload={"entry_id": entry, "payment_id": intent.payment_id, "amount_millimes": intent.amount_millimes,
                               "lines": [{"account": "sandbox_cash", "debit_millimes": intent.amount_millimes},
                                         {"account": "sales_revenue", "credit_millimes": intent.amount_millimes}]})

    def settle_pending(self, payment_id: str, succeed: bool = True) -> PaymentIntent | None:
        """Bank transfer arrives (or a timed-out payment resolves). Sandbox only."""
        p = self.repo.get_payment(payment_id)
        if p is None or p.status != PaymentStatus.PENDING:
            return p
        p.status = PaymentStatus.SUCCEEDED if succeed else PaymentStatus.DECLINED
        p.reason = None if succeed else "processor_declined_after_timeout"
        p.updated_at = utcnow()
        self.repo.update_payment(p)
        self.bus.emit(EventType.PAYMENT_UPDATED, tenant_id=p.tenant_id, case_id=p.case_id, run_id=p.run_id,
                      source="sandouk_pay", target="sandouk",
                      summary=f"SIMULATED payment {fmt_tnd(p.amount_millimes)} is now {p.status.value}",
                      payload=p.model_dump(mode="json"))
        if p.status == PaymentStatus.SUCCEEDED:
            self._post(p, None)
        return p
