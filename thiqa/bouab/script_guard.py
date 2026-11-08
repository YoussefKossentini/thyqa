"""Checks Le Renard's script proposals against rules that no script may change."""
from __future__ import annotations

from ..schemas import ObjectionStrategy, Reason, ScriptVersion
from ..tenants import TenantPack

EDITABLE_FIELDS = {"opening", "pitch_focus", "objection_strategies", "lead_with_monthly_price", "max_discount_percent"}


def script_diff(current: ScriptVersion, proposed: ScriptVersion) -> dict[str, dict]:
    a, b = current.model_dump(mode="json"), proposed.model_dump(mode="json")
    skip = {"version", "status", "proposed_by", "based_on_run", "rationale_ref", "created_at"}
    return {k: {"from": a.get(k), "to": b.get(k)} for k in b if k not in skip and a.get(k) != b.get(k)}


def check_script(proposed: ScriptVersion, current: ScriptVersion, tenant: TenantPack, next_version: int) -> tuple[list[Reason], dict]:
    reasons: list[Reason] = []
    diff = script_diff(current, proposed)

    def no(code: str, message: str) -> None:
        reasons.append(Reason(code=code, rule_id="S", message=message))

    if proposed.tenant_id != tenant.tenant_id:
        no("S01_TENANT", "Script belongs to another tenant")
    if proposed.version != next_version:
        no("S02_VERSION", f"Expected version {next_version}")
    if not proposed.disclosure_line:
        no("S03_DISCLOSURE", "The AI + sandbox disclosure line cannot be removed")
    if proposed.max_discount_percent > tenant.max_discount_percent:
        no("S04_DISCOUNT_CAP", f"Max discount is {tenant.max_discount_percent}% for this tenant")
    strategies = set(proposed.objection_strategies.values())
    if ObjectionStrategy.INSTALLMENTS_FIRST in strategies and not any(tenant.installment_plans(p.product_id) for p in tenant.catalog):
        no("S05_NO_INSTALLMENTS", "Tenant has no installment plan")
    if ObjectionStrategy.STUDENT_DISCOUNT in strategies and not tenant.discount_codes:
        no("S06_NO_STUDENT_CODE", "Tenant has no student discount code")
    if set(diff) - EDITABLE_FIELDS:
        no("S07_FIELD_LOCKED", f"Locked fields changed: {sorted(set(diff) - EDITABLE_FIELDS)}")
    if not diff:
        no("S08_NO_CHANGE", "Proposal is identical to the active script")
    return reasons, diff
