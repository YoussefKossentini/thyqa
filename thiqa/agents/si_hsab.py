"""Si Hsab, Financial Analyst. Read-only SQL over cases, payments, decisions and events.
Never reads raw client text: only typed fields of the Case File."""
from __future__ import annotations

from collections import Counter

from ..db import Repo
from ..money import fmt_tnd
from ..schemas import (
    ApprovalStatus,
    JourneyState,
    KpiSnapshot,
    Objection,
    ObjectionStat,
    PaymentStatus,
    RevenueLost,
    new_id,
    utcnow,
)
from ..tenants import TenantRegistry


class SiHsab:
    def __init__(self, repo: Repo, tenants: TenantRegistry):
        self.repo = repo
        self.tenants = tenants

    def snapshot(self, tenant_id: str, scope: str = "live", save: bool = False) -> KpiSnapshot:
        run_id = None if scope == "live" else scope
        tenant = self.tenants.get(tenant_id)
        cases = [c for c in self.repo.list_cases(tenant_id, run_id) if any(t.role == "client" for t in c.turns)]
        payments = self.repo.list_payments(tenant_id, run_id)

        interactions = len(cases)
        interested = sum(1 for c in cases if c.offer is not None or (c.intelligence and c.intelligence.radar.intent >= 50))
        offers = sum(1 for c in cases if c.offer is not None)
        paid = [c for c in cases if c.state == JourneyState.PAID]
        status = Counter(p.status for p in payments)

        # decisions that blocked a payment (duplicates are not blocks of a sale)
        rid_sql, rid_args = ("run_id IS NULL", []) if run_id is None else ("run_id = ?", [run_id])
        # nosec B608 below: rid_sql / sec_sql are constant fragments chosen in code; values are bound parameters
        blocked = self.repo.q(f"SELECT COUNT(*) AS n FROM decisions WHERE tenant_id=? AND {rid_sql} AND action='pay.create_intent' "
                              "AND decision='BLOCK' AND doc NOT LIKE '%R04_DUPLICATE%'", [tenant_id, *rid_args])[0]["n"]  # nosec B608
        awaiting = sum(1 for c in cases if c.state == JourneyState.AWAITING_APPROVAL)

        obj_counter: Counter[Objection] = Counter()
        for c in cases:
            obj_counter.update(set(c.objections_seen))
        total_obj = sum(obj_counter.values()) or 1
        top = [ObjectionStat(objection=o, count=n, share=round(n / total_obj, 3)) for o, n in obj_counter.most_common()]

        lost_by: dict[Objection, list[int]] = {}
        for c in cases:
            if c.state == JourneyState.CLOSED_LOST and c.lost_reason:
                prod = tenant.product(c.product_interest or tenant.default_product)
                value = c.offer.total_millimes if c.offer else (prod.price_millimes if prod else 0)
                lost_by.setdefault(c.lost_reason, []).append(value)
        lost = []
        for obj, values in sorted(lost_by.items(), key=lambda kv: -sum(kv[1])):
            total = sum(values)
            lost.append(RevenueLost(
                objection=obj, lost_cases=len(values), revenue_lost_millimes=total,
                formula=f"sum of the catalog price of the product discussed, over the {len(values)} lost cases whose last "
                        f"unresolved objection was '{obj.value}' = {fmt_tnd(total)}"))

        sat = Counter(c.intelligence.satisfaction for c in cases if c.intelligence)
        n_sat = sum(sat.values()) or 1
        sec_sql = "(run_id IS NULL OR substr(run_id, 1, 4) <> 'run_')" if run_id is None else rid_sql
        events = {r["type"]: r["n"] for r in self.repo.q(
            f"SELECT type, COUNT(*) AS n FROM events WHERE tenant_id=? AND {sec_sql} GROUP BY type",  # nosec B608
            [tenant_id, *rid_args])}
        alerts = self.repo.list_alerts(tenant_id, limit=1000, include_runs=run_id is not None)
        if run_id:
            alerts = [a for a in alerts if a.get("run_id") == run_id]
        def in_scope(a) -> bool:
            c = self.repo.get_case(a.case_id)
            rid = c.run_id if c else None
            if run_id is not None:
                return rid == run_id
            return not (rid and rid.startswith(("run_", "redteam_")))
        pending_approvals = len([a for a in self.repo.list_approvals(tenant_id, ApprovalStatus.PENDING) if in_scope(a)])

        snap = KpiSnapshot(
            tenant_id=tenant_id, scope=scope, interactions=interactions, interested=interested, offers_proposed=offers,
            conversions=len(paid), conversion_rate=round(len(paid) / interactions, 3) if interactions else 0.0,
            payments={"succeeded": status.get(PaymentStatus.SUCCEEDED, 0), "declined": status.get(PaymentStatus.DECLINED, 0),
                      "pending": status.get(PaymentStatus.PENDING, 0), "blocked": int(blocked), "awaiting_approval": awaiting},
            revenue_collected_millimes=sum(p.amount_millimes for p in payments if p.status == PaymentStatus.SUCCEEDED),
            contract_value_millimes=sum(c.offer.total_millimes for c in paid if c.offer),
            top_objections=top, revenue_lost_by_objection=lost,
            satisfaction={"positive": sat.get("positive", 0), "neutral": sat.get("neutral", 0), "negative": sat.get("negative", 0),
                          "score_0_100": int(round(50 + 50 * (sat.get("positive", 0) - sat.get("negative", 0)) / n_sat))},
            security={
                "alerts_total": len(alerts),
                "by_type": dict(Counter(a["type"] for a in alerts)),
                "injections_blocked": events.get("guard.input_flagged", 0),
                "tool_denied": events.get("bouab.tool_denied", 0),
                "output_rewrites": events.get("guard.output_rewritten", 0),
                "engine_rejections": events.get("payment.engine_rejected", 0),
                "payments_blocked": int(blocked),
                "approvals_pending": pending_approvals,
                "quarantines_active": len(self.repo.active_quarantines()),
            },
        )
        if save:
            self.repo.save_kpi_snapshot(new_id("kpi"), tenant_id, scope, utcnow().isoformat(), snap.model_dump_json())
        return snap

    def objection_stats(self, snap: KpiSnapshot) -> dict:
        """The only input Le Renard gets: numbers, no text."""
        return {
            "interactions": snap.interactions, "conversion_rate": snap.conversion_rate, "conversions": snap.conversions,
            "offers_proposed": snap.offers_proposed,
            "objections": {o.objection.value: {"count": o.count, "share": o.share} for o in snap.top_objections},
            "revenue_lost_millimes": {r.objection.value: r.revenue_lost_millimes for r in snap.revenue_lost_by_objection},
            "payments": snap.payments, "satisfaction_score": snap.satisfaction.get("score_0_100"),
            "injections_blocked": snap.security.get("injections_blocked", 0),
        }
