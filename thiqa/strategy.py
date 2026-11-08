"""The learning loop: Le Renard proposes -> Bouab checks the diff -> a human activates."""
from __future__ import annotations

from .container import Thiqa
from .schemas import Decision, EventType, ScriptVersion, Severity, utcnow


async def propose(app: Thiqa, tenant_id: str, run_id: str | None = None) -> dict:
    snap = app.si_hsab.snapshot(tenant_id, scope=run_id or "live", save=True)
    stats = app.si_hsab.objection_stats(snap)
    current = app.orch.active_script(tenant_id)
    next_version = app.repo.max_script_version(tenant_id) + 1
    recs, draft, mode = await app.le_renard.propose(snap, stats, current, next_version, run_id)
    app.repo.save_recommendations(recs, run_id, utcnow().isoformat())
    app.bus.emit(EventType.RECOMMENDATIONS, tenant_id=tenant_id, source="le_renard", target="human", mode=mode,
                 summary=f"Zeineb: {len(recs)} recommendation(s) from {snap.scope}"
                         + (f", top: {recs[0].title}" if recs else ""),
                 payload={"recommendations": [r.model_dump(mode="json") for r in recs], "scope": snap.scope, "stats": stats})
    result: dict = {"recommendations": [r.model_dump(mode="json") for r in recs], "mode": mode.value, "draft": None,
                    "check": None, "stats": stats}
    if draft is None:
        return result
    app.repo.save_script(draft)
    app.bus.emit(EventType.SCRIPT_PROPOSED, tenant_id=tenant_id, source="le_renard", target="bouab", mode=mode,
                 summary=f"Zeineb drafted script v{draft.version} (based on {run_id or 'live data'})",
                 payload=draft.model_dump(mode="json"))
    reasons, diff = app.bouab.check_script(draft, current, next_version)
    draft.status = "rejected" if reasons else "checked"
    app.repo.save_script(draft)
    result.update(draft=draft.model_dump(mode="json"),
                  check={"ok": not reasons, "reasons": [r.model_dump() for r in reasons], "diff": diff})
    return result


def activate(app: Thiqa, tenant_id: str, version: int, approver_id: str) -> tuple[bool, str, ScriptVersion | None]:
    tenant = app.tenants.get(tenant_id)
    if approver_id not in tenant.approvers:
        return False, f"{approver_id} is not a human approver for {tenant_id}", None
    script = app.repo.get_script(tenant_id, version)
    if script is None:
        return False, "no such script", None
    if script.status != "checked":
        return False, f"script v{version} is '{script.status}': only a Fouchika-checked draft can be activated", None
    current = app.repo.active_script(tenant_id)
    if current:
        current.status = "retired"
        app.repo.save_script(current)
    script.status = "active"
    app.repo.save_script(script)
    app.bus.emit(EventType.SCRIPT_ACTIVATED, tenant_id=tenant_id, source=f"human:{approver_id}", target="sahbi",
                 decision=Decision.ALLOW, severity=Severity.MEDIUM,
                 summary=f"{approver_id} activated script v{version} (was v{current.version if current else '-'})",
                 payload={"version": version, "previous": current.version if current else None, "approver_id": approver_id})
    return True, "activated", script
