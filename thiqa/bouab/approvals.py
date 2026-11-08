"""Human approvals: bound to the request hash, single use, expiring, approver != requester,
two different approvers above 2x the threshold. A BLOCK never becomes an approval."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ..db import Repo
from ..schemas import Approval, ApprovalStatus, Reason, new_id, utcnow
from ..tenants import TenantPack


@dataclass
class ApprovalResult:
    ok: bool
    approval: Approval | None
    refusal: str | None = None     # self_approval | replay | hash_mismatch | expired | not_an_approver | duplicate_vote | not_found | not_pending | not_approved
    message: str = ""


class ApprovalManager:
    def __init__(self, repo: Repo):
        self.repo = repo

    def create(self, *, tenant: TenantPack, case_id: str, payment_id: str, decision_id: str, request_hash: str,
               amount_millimes: int, currency: str, customer_ref: str, product_name: str, requested_by: str,
               reasons: list[Reason], risk_score: int) -> Approval:
        th = tenant.thresholds
        required = 2 if amount_millimes > th.approval_threshold_millimes * th.two_approver_multiplier else 1
        approval = Approval(
            approval_id=new_id("apr"), tenant_id=tenant.tenant_id, case_id=case_id, payment_id=payment_id,
            decision_id=decision_id, request_hash=request_hash, amount_millimes=amount_millimes, currency=currency,
            customer_ref=customer_ref, product_name=product_name, requested_by=requested_by,
            required_approvals=required, reasons=reasons, risk_score=risk_score,
            expires_at=utcnow() + timedelta(seconds=th.approval_ttl_seconds),
        )
        self.repo.save_approval(approval)
        return approval

    def _load(self, approval_id: str) -> Approval | None:
        a = self.repo.get_approval(approval_id)
        if a and a.status in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED) and utcnow() > a.expires_at:
            a.status = ApprovalStatus.EXPIRED
            self.repo.save_approval(a)
        return a

    def get(self, approval_id: str) -> Approval | None:
        return self._load(approval_id)

    def vote(self, approval_id: str, approver_id: str, tenant: TenantPack) -> ApprovalResult:
        a = self._load(approval_id)
        if a is None or a.tenant_id != tenant.tenant_id:
            return ApprovalResult(False, None, "not_found", "No such approval for this tenant")
        if a.status == ApprovalStatus.CONSUMED:
            return ApprovalResult(False, a, "replay", "This approval was already used")
        if a.status == ApprovalStatus.EXPIRED:
            return ApprovalResult(False, a, "expired", "This approval expired")
        if a.status != ApprovalStatus.PENDING:
            return ApprovalResult(False, a, "not_pending", f"Approval is {a.status.value}")
        if approver_id not in tenant.approvers:
            return ApprovalResult(False, a, "not_an_approver", f"{approver_id} is not an approver for {tenant.tenant_id}")
        if approver_id == a.requested_by:
            return ApprovalResult(False, a, "self_approval", "The requester cannot approve its own request")
        if approver_id in a.approvals:
            return ApprovalResult(False, a, "duplicate_vote", "Two-person rule: a second, different approver is needed")
        a.approvals.append(approver_id)
        if len(a.approvals) >= a.required_approvals:
            a.status = ApprovalStatus.APPROVED
        self.repo.save_approval(a)
        return ApprovalResult(True, a, None, "approved" if a.status == ApprovalStatus.APPROVED else
                              f"{len(a.approvals)}/{a.required_approvals} approvals")

    def reject(self, approval_id: str, approver_id: str, tenant: TenantPack) -> ApprovalResult:
        a = self._load(approval_id)
        if a is None or a.tenant_id != tenant.tenant_id:
            return ApprovalResult(False, None, "not_found", "No such approval for this tenant")
        if approver_id not in tenant.approvers:
            return ApprovalResult(False, a, "not_an_approver", f"{approver_id} is not an approver")
        if a.status not in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
            return ApprovalResult(False, a, "not_pending", f"Approval is {a.status.value}")
        a.status = ApprovalStatus.REJECTED
        a.approvals.append(f"rejected_by:{approver_id}")
        self.repo.save_approval(a)
        return ApprovalResult(True, a, None, "rejected")

    def consume(self, approval_id: str, request_hash: str, tenant_id: str) -> ApprovalResult:
        """Called by Bouab when execution resumes. Single use, bound to the exact request."""
        a = self._load(approval_id)
        if a is None or a.tenant_id != tenant_id:
            return ApprovalResult(False, None, "not_found", "No such approval")
        if a.request_hash != request_hash:
            return ApprovalResult(False, a, "hash_mismatch", "The request changed after approval (amount, payment, customer or key)")
        if a.status == ApprovalStatus.CONSUMED:
            return ApprovalResult(False, a, "replay", "Approval already used once")
        if a.status == ApprovalStatus.EXPIRED:
            return ApprovalResult(False, a, "expired", "Approval expired")
        if a.status != ApprovalStatus.APPROVED:
            return ApprovalResult(False, a, "not_approved", f"Approval is {a.status.value}")
        a.status = ApprovalStatus.CONSUMED
        a.consumed_at = utcnow()
        self.repo.save_approval(a)
        return ApprovalResult(True, a, None, "consumed")
