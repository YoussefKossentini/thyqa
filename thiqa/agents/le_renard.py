"""Le Renard, Strategy. Reads aggregated numbers only (typed), recommends with evidence
and drafts script v(N+1). It cannot activate a script: Bouab checks it, a human activates it."""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..llm import LLMGateway
from ..money import fmt_tnd


def _pct(share: float) -> str:
    """0.46 -> '46 %' (French spacing, no-break space written as an escape)."""
    return f"{round(share * 100)}\u00a0%"
from ..schemas import (
    AIMode,
    Evidence,
    KpiSnapshot,
    Objection,
    ObjectionStrategy,
    Recommendation,
    ScriptVersion,
    new_id,
)
from .prompts import LE_RENARD_SYSTEM

OS = ObjectionStrategy
ALLOWED_FIELDS = {"opening", "pitch_focus", "objection_strategies", "lead_with_monthly_price"}


def _share(snap: KpiSnapshot, obj: Objection) -> float:
    return next((o.share for o in snap.top_objections if o.objection == obj), 0.0)


def _lost(snap: KpiSnapshot, obj: Objection) -> int:
    return next((r.revenue_lost_millimes for r in snap.revenue_lost_by_objection if r.objection == obj), 0)


def mock_recommendations(snap: KpiSnapshot, current: ScriptVersion) -> list[Recommendation]:
    scope = snap.scope
    recs: list[Recommendation] = []
    price = _share(snap, Objection.PRICE)
    if price >= 0.25 and not current.lead_with_monthly_price:
        recs.append(Recommendation(
            rec_id=new_id("rec"), tenant_id=snap.tenant_id, priority="high",
            title="Annoncer d'abord le prix mensuel et proposer les tranches",
            rationale=f"{_pct(price)} des objections portent sur le prix, et les objections prix restées sans réponse ont coûté "
                      f"{fmt_tnd(_lost(snap, Objection.PRICE), 'fr')}. Donner le montant par mois avant le prix total.",
            evidence=[Evidence(metric="price_objection_share", value=price, scope=scope),
                      Evidence(metric="revenue_lost_price_millimes", value=_lost(snap, Objection.PRICE), scope=scope),
                      Evidence(metric="conversion_rate", value=snap.conversion_rate, scope=scope)],
            proposed_change={"lead_with_monthly_price": True,
                             "objection_strategies": {Objection.PRICE.value: OS.INSTALLMENTS_FIRST.value}}))
    trust = _share(snap, Objection.TRUST)
    if trust >= 0.12 and current.objection_strategies.get(Objection.TRUST) != OS.SHOW_PROGRAM:
        recs.append(Recommendation(
            rec_id=new_id("rec"), tenant_id=snap.tenant_id, priority="medium",
            title="Répondre aux doutes avec le programme complet et un appel avec un formateur",
            rationale=f"{_pct(trust)} des objections portent sur la confiance ; les ventes perdues sur ce point valent {fmt_tnd(_lost(snap, Objection.TRUST), 'fr')}.",
            evidence=[Evidence(metric="trust_objection_share", value=trust, scope=scope),
                      Evidence(metric="revenue_lost_trust_millimes", value=_lost(snap, Objection.TRUST), scope=scope)],
            proposed_change={"objection_strategies": {Objection.TRUST.value: OS.SHOW_PROGRAM.value}}))
    time_share = _share(snap, Objection.TIME)
    if time_share >= 0.12 and "schedule" not in current.pitch_focus:
        recs.append(Recommendation(
            rec_id=new_id("rec"), tenant_id=snap.tenant_id, priority="low",
            title="Mettre les horaires dans le pitch",
            rationale=f"{_pct(time_share)} des objections portent sur le temps ; dire tout de suite que les cours sont le soir et le week-end.",
            evidence=[Evidence(metric="time_objection_share", value=time_share, scope=scope)],
            proposed_change={"pitch_focus": (current.pitch_focus[:2] + ["schedule"])}))
    declined = snap.payments.get("declined", 0)
    if declined >= 2:
        recs.append(Recommendation(
            rec_id=new_id("rec"), tenant_id=snap.tenant_id, priority="low",
            title="Après un refus pour solde insuffisant, proposer les tranches ou le virement",
            rationale=f"{declined} paiements refusés ; Janet propose déjà un plan de relance, Sboui doit le dire au client.",
            evidence=[Evidence(metric="payments_declined", value=declined, scope=scope)], proposed_change=None))
    return recs[:3]


def apply_changes(current: ScriptVersion, recs: list[Recommendation], next_version: int, run_id: str | None) -> ScriptVersion | None:
    data = current.model_dump(mode="json")
    changed = False
    for rec in recs:
        for key, value in (rec.proposed_change or {}).items():
            if key not in ALLOWED_FIELDS:
                continue
            if key == "objection_strategies" and isinstance(value, dict):
                data["objection_strategies"] = {**data["objection_strategies"], **value}
            else:
                data[key] = value
            changed = True
    if not changed:
        return None
    data.update({"version": next_version, "status": "draft", "proposed_by": "le_renard", "based_on_run": run_id,
                 "rationale_ref": recs[0].rec_id if recs else None})
    data.pop("created_at", None)
    try:
        return ScriptVersion.model_validate(data)
    except ValidationError:
        return None


class LeRenard:
    def __init__(self, llm: LLMGateway):
        self.llm = llm

    async def propose(self, snap: KpiSnapshot, stats: dict[str, Any], current: ScriptVersion, next_version: int,
                      run_id: str | None) -> tuple[list[Recommendation], ScriptVersion | None, AIMode]:
        recs, mode = mock_recommendations(snap, current), AIMode.MOCK
        if self.llm.mode != "mock":
            res = await self.llm.complete_json(
                "le_renard", LE_RENARD_SYSTEM,
                [{"role": "user", "content": json.dumps({"stats": stats, "current_script": current.model_dump(
                    mode="json", include=ALLOWED_FIELDS)}, ensure_ascii=False)}],
                context_key=f"{snap.tenant_id}:{current.version}", temperature=0.3, max_tokens=600)
            parsed = self._parse(res.data if res else None, snap)
            if parsed:
                recs, mode = parsed, res.mode  # type: ignore[union-attr]
        for r in recs:
            r.mode = mode
        return recs, apply_changes(current, recs, next_version, run_id), mode

    @staticmethod
    def _parse(data: dict | None, snap: KpiSnapshot) -> list[Recommendation] | None:
        if not data or not isinstance(data.get("recommendations"), list):
            return None
        out = []
        for item in data["recommendations"][:3]:
            try:
                change = item.get("proposed_change") if isinstance(item.get("proposed_change"), dict) else None
                if change:
                    change = {k: v for k, v in change.items() if k in ALLOWED_FIELDS}
                out.append(Recommendation(
                    rec_id=new_id("rec"), tenant_id=snap.tenant_id, title=str(item.get("title", ""))[:140] or "Recommendation",
                    rationale=str(item.get("rationale", ""))[:480],
                    priority=item.get("priority") if item.get("priority") in ("high", "medium", "low") else "medium",
                    evidence=[Evidence(metric=str(e.get("metric", ""))[:60], value=e.get("value") if isinstance(e.get("value"), (int, float)) else str(e.get("value"))[:60], scope=snap.scope)
                              for e in (item.get("evidence") or [])[:4] if isinstance(e, dict)],
                    proposed_change=change or None))
            except (ValidationError, AttributeError, TypeError):
                continue
        return out or None
