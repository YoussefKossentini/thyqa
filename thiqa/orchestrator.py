"""Orchestrator: the journey state machine and the only writer of CaseFile.state.

Two paths, never mixed:
  * money path (hot, no LLM): offer accepted -> Bouab -> (approval) -> signed
    authorization -> Sandouk Pay -> ledger -> KPIs. Deterministic.
  * AI path (cold, may degrade): Sahbi replies, Fahem analyses in parallel,
    Le Renard recommends. Timeouts and MOCK fallback; it never blocks money.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

from .agents.fahem import Fahem
from .agents.lexicon import is_explicit_confirmation, product_mentioned
from .agents.le_renard import LeRenard
from .agents.sahbi import Sahbi, opening_line
from .agents.sandouk import build_request, retry_plan
from .agents.si_hsab import SiHsab
from .bouab.approvals import ApprovalResult
from .bouab.core import Bouab
from .bouab.input_guard import CANNED_REPLY, guess_lang
from .bus import EventBus
from .db import Repo
from .money import fmt_tnd
from .pay.engine import EngineRejected, SandoukPay
from .schemas import (
    TRANSITIONS,
    ActionRequest,
    AIMode,
    ApprovalStatus,
    CaseFile,
    Channel,
    Decision,
    EventType,
    Intent,
    JourneyState,
    Lang,
    Objection,
    ObjectionStrategy,
    PaymentIntent,
    PaymentStatus,
    SahbiAction,
    SahbiReply,
    SandboxToken,
    ScriptVersion,
    Severity,
    ToolDecision,
    Turn,
    TurnResult,
    new_id,
    utcnow,
)
from .tenants import TenantRegistry

ET = EventType
JS = JourneyState

OUTCOME_TEXT: dict[str, dict[str, str]] = {
    "paid": {"derja": "Mabrouk! El paiement (test) mta3 {amount} t3adda. Mar7ba bik fi {name}!",
             "fr": "Félicitations ! Le paiement test de {amount} est validé. Bienvenue dans {name} !",
             "en": "Done! The test payment of {amount} went through. Welcome to {name}!"},
    "awaiting_approval": {"derja": "El montant hedha ({amount}) yest7a9 validation men 3and el équipe. D9i9a w nraj3oulek.",
                          "fr": "Ce montant ({amount}) doit être validé par l'équipe. Je reviens vers vous très vite.",
                          "en": "This amount ({amount}) needs a validation by the team. I'll be right back."},
    "pending_timeout": {"derja": "El paiement mazal en attente (test). Nraj3oulek ki yetsakker.",
                        "fr": "Le paiement test est encore en attente. Je vous confirme dès qu'il passe.",
                        "en": "The test payment is still pending. I'll confirm as soon as it clears."},
    "pending_transfer": {"derja": "Behi, nestannew el virement (simulé) mta3 {amount}. Ki youssel nab3athlek confirmation.",
                         "fr": "Très bien, nous attendons le virement simulé de {amount}. Je confirme à réception.",
                         "en": "Fine, we are waiting for the simulated transfer of {amount}. I'll confirm on arrival."},
    "declined_insufficient": {"derja": "El paiement ma t3addech (solde insuffisant). Tnajjem tkhallas 3la marrat walla b virement.",
                              "fr": "Le paiement n'est pas passé (solde insuffisant). Vous pouvez payer en plusieurs fois ou par virement.",
                              "en": "The payment did not go through (insufficient funds). You can pay in installments or by transfer."},
    "declined_fraud": {"derja": "El banque (test) 7abset el paiement l-asbab amniya. El équipe bech tetwasel m3ak.",
                       "fr": "La banque test a bloqué le paiement pour raison de sécurité. L'équipe va vous contacter.",
                       "en": "The test bank stopped the payment for security reasons. The team will contact you."},
    "declined_other": {"derja": "El paiement ma t3addech. Tnajjem t3awed walla tbaddel el méthode.",
                       "fr": "Le paiement n'est pas passé. Vous pouvez réessayer ou changer de méthode.",
                       "en": "The payment did not go through. You can retry or change the method."},
    "blocked": {"derja": "El demande hadhi ma najjamnech nkammlouha. El équipe bech traja3ha.",
                "fr": "Nous ne pouvons pas finaliser cette demande. L'équipe va l'examiner.",
                "en": "We can't complete this request. The team will review it."},
    "duplicate": {"derja": "El paiement mte3ek deja ta3ada, ma fammech paiement thani.",
                  "fr": "Votre paiement est déjà pris en compte, il n'y aura pas de second débit.",
                  "en": "Your payment is already being handled; there won't be a second charge."},
    "rejected_by_team": {"derja": "El équipe ma waf9etch 3al paiement hedha. Tnajjem tkhallas 3la marrat?",
                         "fr": "L'équipe n'a pas validé ce paiement. Voulez-vous payer en plusieurs fois ?",
                         "en": "The team did not approve this payment. Would installments work for you?"},
    "case_blocked": {"derja": "El mou7adtha hadhi t7abset l-asbab amniya. El équipe bech traja3ha.",
                     "fr": "Cette conversation est suspendue pour raison de sécurité. L'équipe va l'examiner.",
                     "en": "This conversation is on hold for security reasons. The team will review it."},
    "no_offer": {"derja": "Ma fammech offre bech tconfirmiha tawa. T7eb nhadhrolek wa7da?",
                 "fr": "Il n'y a pas d'offre à confirmer pour l'instant. Je vous en prépare une ?",
                 "en": "There's no offer to confirm yet. Shall I prepare one?"},
    "offer_changed": {"derja": "El offre tbaddlet. Chouf el offre el jdida 9bal ma tconfirmi.",
                      "fr": "L'offre a changé. Merci de vérifier la nouvelle offre avant de confirmer.",
                      "en": "The offer changed. Please check the new one before confirming."},
}


def _lk(lang: Lang) -> str:
    return {Lang.FR: "fr", Lang.EN: "en"}.get(lang, "derja")


def default_script(tenant_id: str) -> ScriptVersion:
    """Script v1: the baseline the team wrote by hand before any run."""
    return ScriptVersion(
        tenant_id=tenant_id, version=1, status="active", opening="warm_short", pitch_focus=["outcomes", "projects"],
        objection_strategies={
            Objection.PRICE: ObjectionStrategy.VALUE_FIRST,
            Objection.TRUST: ObjectionStrategy.VALUE_FIRST,
            Objection.TIME: ObjectionStrategy.FLEXIBLE_SCHEDULE,
            Objection.RELEVANCE: ObjectionStrategy.VALUE_FIRST,
            Objection.COMPREHENSION: ObjectionStrategy.SIMPLIFY,
            Objection.PAYMENT_METHOD: ObjectionStrategy.VALUE_FIRST,
        },
        lead_with_monthly_price=False, max_discount_percent=10, disclosure_line=True, proposed_by="human",
    )


@dataclass
class PayOutcome:
    kind: str
    payment: PaymentIntent | None = None
    decision: ToolDecision | None = None


class Orchestrator:
    def __init__(self, *, repo: Repo, bus: EventBus, tenants: TenantRegistry, bouab: Bouab, engine: SandoukPay,
                 sahbi: Sahbi, fahem: Fahem, si_hsab: SiHsab, le_renard: LeRenard, agent_timeout_s: float = 12.0):
        self.repo = repo
        self.bus = bus
        self.tenants = tenants
        self.bouab = bouab
        self.engine = engine
        self.sahbi = sahbi
        self.fahem = fahem
        self.si_hsab = si_hsab
        self.le_renard = le_renard
        self.agent_timeout_s = agent_timeout_s
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ scripts
    def active_script(self, tenant_id: str) -> ScriptVersion:
        s = self.repo.active_script(tenant_id)
        if s is None:
            s = default_script(tenant_id)
            self.repo.save_script(s)
        return s

    def script_for(self, case: CaseFile) -> ScriptVersion:
        return self.repo.get_script(case.tenant_id, case.script_version) or self.active_script(case.tenant_id)

    # ------------------------------------------------------------------ helpers
    def _transition(self, case: CaseFile, new: JourneyState, why: str, corr: str) -> None:
        old = case.state
        if new == old and new != JS.OFFER_PROPOSED:
            return
        if new not in TRANSITIONS[old]:
            raise RuntimeError(f"illegal transition {old.value} -> {new.value}")
        case.state = new
        case.updated_at = utcnow()
        self.bus.emit(ET.STATE_CHANGED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                      correlation_id=corr, source="orchestrator", summary=f"Case {old.value} -> {new.value} ({why})",
                      severity=Severity.HIGH if new == JS.BLOCKED else Severity.INFO,
                      payload={"from": old.value, "to": new.value, "why": why})

    def _save(self, case: CaseFile) -> None:
        case.updated_at = utcnow()
        self.repo.save_case(case)

    def _load(self, case_id: str, tenant_id: str | None = None) -> CaseFile:
        case = self.repo.get_case(case_id)
        if case is None or (tenant_id and case.tenant_id != tenant_id):
            raise KeyError("case not found")
        return case

    def _lang(self, case: CaseFile) -> Lang:
        last = next((t.text for t in reversed(case.turns) if t.role == "client" and not t.withheld), "")
        return guess_lang(last) if last else Lang.DERJA

    def _say(self, case: CaseFile, key: str, corr: str, **fmt) -> str:
        text = OUTCOME_TEXT[key][_lk(self._lang(case))].format(**fmt)
        case.turns.append(Turn(turn_id=new_id("t"), role="sahbi", text=text, mode=AIMode.MOCK))
        self.bus.emit(ET.TURN_SAHBI, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                      correlation_id=corr, source="sahbi", target="client", mode=AIMode.MOCK,
                      summary=f"Sboui: {text[:120]}", payload={"text": text, "template": key})
        return text

    def _kpis(self, case: CaseFile) -> None:
        if case.run_id:
            return
        snap = self.si_hsab.snapshot(case.tenant_id)
        self.bus.emit(ET.KPI_UPDATED, tenant_id=case.tenant_id, source="si_hsab", summary=(
            f"Dalenda: {snap.interactions} interactions, conversion {snap.conversion_rate:.0%}, "
            f"revenue {fmt_tnd(snap.revenue_collected_millimes)} (simulated)"), payload=snap.model_dump(mode="json"))

    def _result(self, case: CaseFile, reply: str, mode: AIMode, **extra) -> TurnResult:
        return TurnResult(case_id=case.case_id, reply=reply, mode=mode, state=case.state, offer=case.offer,
                          radar=case.intelligence.radar if case.intelligence else None, **extra)

    # ------------------------------------------------------------------ open
    async def open_case(self, tenant_id: str, channel: Channel = Channel.TEXT, customer_ref: str | None = None,
                        run_id: str | None = None, lang: Lang = Lang.DERJA,
                        script_version: int | None = None) -> tuple[CaseFile, str]:
        tenant = self.tenants.get(tenant_id)
        script = self.repo.get_script(tenant_id, script_version) if script_version else None
        script = script or self.active_script(tenant_id)
        case = CaseFile(case_id=new_id("case"), tenant_id=tenant_id, customer_ref=customer_ref or new_id("cus"),
                        channel=channel, run_id=run_id, script_version=script.version)
        corr = new_id("cor")
        self.bus.emit(ET.CASE_OPENED, tenant_id=tenant_id, case_id=case.case_id, run_id=run_id, correlation_id=corr,
                      source="orchestrator", summary=f"New {channel.value} case for {tenant.display_name} (script v{script.version})",
                      payload={"channel": channel.value, "customer_ref": case.customer_ref, "script_version": script.version})
        self._transition(case, JS.CONVERSING, "client connected", corr)
        text = self.bouab.screen_output(case, opening_line(tenant, script, lang), corr, lang).text
        case.turns.append(Turn(turn_id=new_id("t"), role="sahbi", text=text, mode=AIMode.MOCK))
        self.bus.emit(ET.TURN_SAHBI, tenant_id=tenant_id, case_id=case.case_id, run_id=run_id, correlation_id=corr,
                      source="sahbi", target="client", mode=AIMode.MOCK, summary=f"Sboui: {text[:120]}",
                      payload={"text": text, "template": "opening"})
        self._save(case)
        return case, text

    # ------------------------------------------------------------------ turn
    async def handle_turn(self, case_id: str, text: str, payment_method: str | None = None,
                          tenant_id: str | None = None) -> TurnResult:
        async with self._locks[case_id]:
            case = self._load(case_id, tenant_id)
            tenant = self.tenants.get(case.tenant_id)
            corr = new_id("cor")
            if payment_method and payment_method in SandboxToken._value2member_map_:
                case.payment_method = payment_method
            if case.state == JS.BLOCKED:
                return self._result(case, OUTCOME_TEXT["case_blocked"][_lk(guess_lang(text))], AIMode.MOCK,
                                    decision=Decision.BLOCK, notice="case blocked by Fouchika")

            # 1. Bouab input guard: flagged text never reaches Sahbi
            verdict = self.bouab.screen_input(case, text, corr)
            if verdict.flagged:
                case.turns.append(Turn(turn_id=new_id("t"), role="client", text="[message withheld by Fouchika]", withheld=True))
                if self.bouab.should_block_case(case):
                    self._transition(case, JS.BLOCKED, f"case risk {self.bouab.case_risk(case)} after repeated injections", corr)
                    reply = OUTCOME_TEXT["case_blocked"][_lk(verdict.lang)]
                else:
                    reply = CANNED_REPLY[verdict.lang]
                case.turns.append(Turn(turn_id=new_id("t"), role="sahbi", text=reply, mode=AIMode.MOCK))
                self.bus.emit(ET.TURN_SAHBI, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                              correlation_id=corr, source="sahbi", target="client", mode=AIMode.MOCK,
                              summary=f"Sboui (safe reply): {reply[:100]}", payload={"text": reply, "template": "withheld"})
                self._save(case)
                return self._result(case, reply, AIMode.MOCK, withheld=True, decision=Decision.BLOCK,
                                    notice="message withheld by Fouchika")

            case.turns.append(Turn(turn_id=new_id("t"), role="client", text=text))
            pid = product_mentioned(text, [p.product_id for p in tenant.catalog])
            if pid:
                case.product_interest = pid
            self.bus.emit(ET.TURN_CLIENT, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="client", target="sahbi", summary=f"Client: {text[:120]}",
                          payload={"text": text, "lang": verdict.lang.value})

            # 2. Deterministic confirmation (never an LLM opinion)
            if case.offer and case.state in (JS.OFFER_PROPOSED, JS.PAYMENT_FAILED) and is_explicit_confirmation(text):
                return await self._confirm(case, case.offer.offer_hash, case.payment_method, corr)

            # 3. AI path: Sahbi and Fahem in parallel, with timeouts and MOCK fallback.
            #    Each agent reads the transcript through Bouab: a quarantined agent does not run.
            script = self.script_for(case)
            sahbi_ok = self._may_read("sahbi", case, corr)
            fahem_ok = self._may_read("fahem", case, corr)
            sahbi_job = (self._timed(self.sahbi.reply(case, tenant, script), "sahbi", case, tenant, script) if sahbi_ok
                         else self._paused_reply(case))
            fahem_job = (self._timed(self.fahem.analyze(case), "fahem", case, tenant, script) if fahem_ok
                         else self._timed(self._noop_analysis(case), "fahem", case, tenant, script))
            (reply, s_mode), (analysis, f_mode) = await asyncio.gather(sahbi_job, fahem_job)
            self._apply_analysis(case, analysis)
            self.bus.emit(ET.FAHEM_ANALYSIS, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="fahem", target="orchestrator", mode=f_mode,
                          summary=(f"Dr. Slimane: {analysis.intent.value}"
                                   + (f", objections {', '.join(o.value for o in analysis.objections)}" if analysis.objections else "")
                                   + f", persona {analysis.persona.value}"),
                          payload={**analysis.model_dump(mode="json"), "checks": ["transcript.read:ALLOW", "intelligence.write:ALLOW"]})

            # 4. Bouab output guard on every reply
            out = self.bouab.screen_output(case, reply.text, corr, analysis.lang)
            notice = None
            if reply.action == SahbiAction.PROPOSE_OFFER and reply.product_id and reply.plan_id:
                offer = self._build_offer(case, tenant, reply.product_id, reply.plan_id, reply.discount_code)
                if offer:
                    case.offer = offer
                    case.product_interest = offer.product_id
                    if case.state in (JS.CONVERSING, JS.OFFER_PROPOSED, JS.PAYMENT_FAILED):
                        self._transition(case, JS.OFFER_PROPOSED, "Sboui proposed an offer", corr)
                    self.bus.emit(ET.OFFER_PROPOSED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                                  correlation_id=corr, source="sahbi", target="client",
                                  summary=f"Offer: {offer.product_name}, {offer.installments}x, due now {fmt_tnd(offer.due_now_millimes)} (SIMULATED)",
                                  payload=offer.model_dump(mode="json"))
                    notice = "offer on the table: confirm to pay (sandbox)"
            elif reply.action == SahbiAction.CLOSE and case.state in (JS.CONVERSING, JS.OFFER_PROPOSED):
                self._close(case, "client declined", corr)

            case.turns.append(Turn(turn_id=new_id("t"), role="sahbi", text=out.text, mode=s_mode))
            self.bus.emit(ET.TURN_SAHBI, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="sahbi", target="client", mode=s_mode,
                          summary=f"Sboui: {out.text[:120]}",
                          payload={"text": out.text, "rewritten": out.rewritten, "action": reply.action.value,
                                   "checks": ["transcript.read:ALLOW", "catalog.read:ALLOW", "turn.append:ALLOW",
                                              "output_guard:" + ("REWRITTEN" if out.rewritten else "ALLOW")]})
            self._save(case)
            if not case.run_id and len(case.turns) % 4 == 0:
                self._kpis(case)
            return self._result(case, out.text, s_mode, notice=notice)

    def _may_read(self, agent_id: str, case: CaseFile, corr: str) -> bool:
        self._save(case)
        d = self.bouab.call_tool(ActionRequest(agent_id=agent_id, action="transcript.read", tenant_id=case.tenant_id,
                                               case_id=case.case_id, correlation_id=corr))
        return d.decision == Decision.ALLOW

    async def _paused_reply(self, case: CaseFile):
        text = {"derja": "Sboui m9a33ed tawa men 3and Fouchika (contrôle de sécurité). Wa7ed mel équipe bech ykammel m3ak.",
                "fr": "Sboui est mis en pause par Fouchika (contrôle de sécurité). Un membre de l'équipe prend le relais.",
                "en": "Sboui is paused by Fouchika (security check). A team member will take over."}[_lk(self._lang(case))]
        return SahbiReply(text=text), AIMode.MOCK

    async def _noop_analysis(self, case: CaseFile):
        from .agents.fahem import mock_analysis
        texts = [t.text for t in case.turns if t.role == "client" and not t.withheld]
        return mock_analysis(texts, case.intelligence), AIMode.MOCK

    async def _timed(self, coro, who: str, case: CaseFile, tenant, script):
        try:
            return await asyncio.wait_for(coro, timeout=self.agent_timeout_s)
        except Exception:  # an agent failing never blocks the journey
            if who == "sahbi":
                from .agents.sahbi import mock_reply
                return mock_reply(case, tenant, script), AIMode.MOCK
            from .agents.fahem import mock_analysis
            texts = [t.text for t in case.turns if t.role == "client" and not t.withheld]
            return mock_analysis(texts, case.intelligence), AIMode.MOCK

    def _apply_analysis(self, case: CaseFile, analysis) -> None:
        case.intelligence = analysis
        for obj in analysis.objections:
            if obj not in case.objections_seen:
                case.objections_seen.append(obj)
            if obj in case.objections_resolved:
                case.objections_resolved.remove(obj)
        if analysis.intent in (Intent.PURCHASE_INTENT, Intent.CONFIRM):
            case.objections_resolved = list(case.objections_seen)

    def _build_offer(self, case: CaseFile, tenant, product_id: str, plan_id: str, code: str | None):
        if "full_payment_only" in case.restrictions:
            prod = tenant.product(product_id)
            plan_id = prod.plans[0] if prod else plan_id
        if code:
            dc = tenant.discount(code)
            persona = case.intelligence.persona.value if case.intelligence else "unknown"
            if dc is None or (dc.personas and persona not in [p.value for p in dc.personas]):
                code = None  # Sahbi may not hand out a code the persona is not eligible for
        try:
            return tenant.build_offer(product_id, plan_id, code)
        except ValueError:
            return None

    def _close(self, case: CaseFile, why: str, corr: str) -> None:
        unresolved = [o for o in case.objections_seen if o not in case.objections_resolved]
        case.lost_reason = unresolved[-1] if unresolved else None
        self._transition(case, JS.CLOSED_LOST, why, corr)

    async def close_case(self, case_id: str, tenant_id: str | None = None) -> CaseFile:
        async with self._locks[case_id]:
            case = self._load(case_id, tenant_id)
            if case.state in (JS.CONVERSING, JS.OFFER_PROPOSED, JS.PAYMENT_FAILED, JS.NEW):
                self._close(case, "client left", new_id("cor"))
                self._save(case)
                self._kpis(case)
            return case

    # ------------------------------------------------------------------ money path
    async def confirm(self, case_id: str, offer_hash: str, payment_method: str | None = None,
                      tenant_id: str | None = None) -> TurnResult:
        async with self._locks[case_id]:
            case = self._load(case_id, tenant_id)
            return await self._confirm(case, offer_hash, payment_method, new_id("cor"))

    async def _confirm(self, case: CaseFile, offer_hash: str, method: str | None, corr: str) -> TurnResult:
        if method and method in SandboxToken._value2member_map_:
            case.payment_method = method
        if case.state == JS.BLOCKED:
            return self._result(case, OUTCOME_TEXT["case_blocked"][_lk(self._lang(case))], AIMode.MOCK, decision=Decision.BLOCK)
        if case.offer is None:
            text = self._say(case, "no_offer", corr)
            self._save(case)
            return self._result(case, text, AIMode.MOCK)
        if offer_hash != case.offer.offer_hash:
            text = self._say(case, "offer_changed", corr)
            self._save(case)
            return self._result(case, text, AIMode.MOCK, notice="offer hash mismatch")
        duplicate = case.state in (JS.OFFER_ACCEPTED, JS.AWAITING_APPROVAL, JS.PAYMENT_PENDING, JS.PAID) \
            and case.confirmed_offer_hash == offer_hash
        if not duplicate:
            if case.state not in (JS.OFFER_PROPOSED, JS.PAYMENT_FAILED):
                text = self._say(case, "no_offer", corr)
                self._save(case)
                return self._result(case, text, AIMode.MOCK)
            case.payment_attempt += 1
            case.confirmed_offer_hash = offer_hash
            self._transition(case, JS.OFFER_ACCEPTED, "explicit client confirmation", corr)
            self.bus.emit(ET.OFFER_ACCEPTED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                          correlation_id=corr, source="client", target="sandouk",
                          summary=f"Client confirmed {case.offer.product_name} ({fmt_tnd(case.offer.due_now_millimes)} now, {case.payment_method})",
                          payload={"offer_hash": offer_hash, "method": case.payment_method, "attempt": case.payment_attempt})
        outcome = await self._pay(case, corr)
        return self._finish_payment(case, outcome, corr)

    async def _pay(self, case: CaseFile, corr: str, approval_id: str | None = None,
                   requested_by: str | None = None) -> PayOutcome:
        """Sandouk asks Bouab, then calls Sandouk Pay with the signed authorization. No LLM here."""
        req = build_request(case, corr, approval_id=approval_id, requested_by=requested_by)
        if req.payment_id not in case.payment_ids:
            case.payment_ids.append(req.payment_id or "")
        self._save(case)  # Bouab reads the stored Case File itself, it never trusts the caller's copy
        d = self.bouab.call_tool(req)
        codes = {r.code for r in d.reasons}
        if d.decision == Decision.BLOCK:
            if codes == {"R04_DUPLICATE"}:
                existing = self.repo.get_payment(d.existing_payment_id) if d.existing_payment_id else None
                return PayOutcome("duplicate", existing, d)
            if any(c.startswith("A_") for c in codes) and case.state == JS.AWAITING_APPROVAL:
                return PayOutcome("approval_refused", None, d)
            if "full_payment_only" in d.restrictions and "full_payment_only" not in case.restrictions:
                case.restrictions.append("full_payment_only")
            self._transition(case, JS.BLOCKED, "Fouchika blocked the payment: " + ", ".join(sorted(codes)), corr)
            return PayOutcome("blocked", None, d)
        for r in d.restrictions:
            if r not in case.restrictions:
                case.restrictions.append(r)
        if d.decision == Decision.REQUIRE_APPROVAL:
            case.pending_approval_id = d.approval_id
            if case.state != JS.AWAITING_APPROVAL:
                self._transition(case, JS.AWAITING_APPROVAL, "Fouchika requires a human approval", corr)
            return PayOutcome("awaiting_approval", None, d)
        try:
            intent = self.engine.create_intent(
                payment_id=req.payment_id or "", tenant_id=case.tenant_id, case_id=case.case_id,
                amount_millimes=req.amount_millimes or 0, currency=req.currency or "", method=case.payment_method,
                idempotency_key=req.idempotency_key or "", authorization=d.authorization, caller="sandouk",
                run_id=case.run_id, correlation_id=corr)
        except EngineRejected:
            self._transition(case, JS.BLOCKED, "payment engine rejected the authorization", corr)
            return PayOutcome("blocked", None, d)
        case.pending_approval_id = None
        return self._apply_payment(case, intent, d, corr)

    def _apply_payment(self, case: CaseFile, intent: PaymentIntent, d: ToolDecision | None, corr: str) -> PayOutcome:
        if intent.status == PaymentStatus.SUCCEEDED:
            self._transition(case, JS.PAID, "payment succeeded (sandbox)", corr)
            return PayOutcome("paid", intent, d)
        if intent.status == PaymentStatus.PENDING:
            self._transition(case, JS.PAYMENT_PENDING, intent.reason or "pending", corr)
            return PayOutcome("pending_transfer" if intent.reason == "awaiting_transfer" else "pending_timeout", intent, d)
        self._transition(case, JS.PAYMENT_FAILED, intent.reason or "declined", corr)
        if intent.reason == "suspected_fraud":
            self.bouab.record_signal(case, "processor_fraud_flag", "sandbox processor flagged the last attempt")
        plan = retry_plan(intent, case, self.tenants.get(case.tenant_id))
        self.bus.emit(ET.RETRY_PROPOSED, tenant_id=case.tenant_id, case_id=case.case_id, run_id=case.run_id,
                      correlation_id=corr, source="sandouk", target="sahbi",
                      summary=f"Janet: retry plan after {plan.reason}: {', '.join(o.value for o in plan.options)}",
                      payload=plan.model_dump(mode="json"))
        kind = {"insufficient_funds": "declined_insufficient", "suspected_fraud": "declined_fraud"}.get(intent.reason or "", "declined_other")
        return PayOutcome(kind, intent, d)

    def _finish_payment(self, case: CaseFile, outcome: PayOutcome, corr: str) -> TurnResult:
        offer = case.offer
        amount = fmt_tnd(offer.due_now_millimes, "derja") if offer else ""
        name = offer.product_name if offer else ""
        key = outcome.kind if outcome.kind in OUTCOME_TEXT else "blocked"
        text = self._say(case, key, corr, amount=amount, name=name)
        self._save(case)
        self._kpis(case)
        return self._result(case, text, AIMode.MOCK, payment=outcome.payment,
                            decision=outcome.decision.decision if outcome.decision else None,
                            notice={"duplicate": "duplicate request: one payment only",
                                    "awaiting_approval": f"approval {case.pending_approval_id} pending"}.get(outcome.kind))

    # ------------------------------------------------------------------ approvals (humans)
    async def vote(self, approval_id: str, approver_id: str, channel: str = "dashboard") -> tuple[ApprovalResult, TurnResult | None]:
        approval = self.repo.get_approval(approval_id)
        if approval is None:
            return ApprovalResult(False, None, "not_found", "No such approval"), None
        tenant = self.tenants.get(approval.tenant_id)
        res = self.bouab.approvals.vote(approval_id, approver_id, tenant)
        corr = new_id("cor")
        if not res.ok:
            self.bus.emit(ET.APPROVAL_REFUSED, tenant_id=approval.tenant_id, case_id=approval.case_id, correlation_id=corr,
                          source=f"human:{approver_id}", target="bouab", decision=Decision.BLOCK,
                          severity=Severity.HIGH if res.refusal in ("self_approval", "replay", "hash_mismatch") else Severity.MEDIUM,
                          summary=f"Fouchika refused {approver_id}'s vote: {res.message}",
                          payload={"approval_id": approval_id, "approver_id": approver_id, "refusal": res.refusal, "channel": channel})
            return res, None
        a = res.approval
        if a is None:
            return res, None
        self.bus.emit(ET.APPROVAL_VOTE, tenant_id=a.tenant_id, case_id=a.case_id, correlation_id=corr,
                      source=f"human:{approver_id}", target="bouab", decision=Decision.ALLOW,
                      summary=f"{approver_id} approved via {channel} ({len(a.approvals)}/{a.required_approvals})",
                      payload={"approval_id": a.approval_id, "approver_id": approver_id, "channel": channel,
                               "approvals": a.approvals, "required": a.required_approvals})
        if a.status != ApprovalStatus.APPROVED:
            return res, None
        self.bus.emit(ET.APPROVAL_GRANTED, tenant_id=a.tenant_id, case_id=a.case_id, correlation_id=corr,
                      source=f"human:{approver_id}", target="sandouk", decision=Decision.ALLOW,
                      summary=f"Approved: {fmt_tnd(a.amount_millimes)} for {a.product_name} by {', '.join(a.approvals)}",
                      payload={"approval_id": a.approval_id, "approvers": a.approvals})
        async with self._locks[a.case_id]:
            case = self._load(a.case_id)
            if case.state != JS.AWAITING_APPROVAL or case.pending_approval_id != a.approval_id:
                return res, None
            outcome = await self._pay(case, corr, approval_id=a.approval_id)
            return res, self._finish_payment(case, outcome, corr)

    async def reject(self, approval_id: str, approver_id: str) -> ApprovalResult:
        approval = self.repo.get_approval(approval_id)
        if approval is None:
            return ApprovalResult(False, None, "not_found", "No such approval")
        res = self.bouab.approvals.reject(approval_id, approver_id, self.tenants.get(approval.tenant_id))
        if not res.ok:
            return res
        corr = new_id("cor")
        self.bus.emit(ET.APPROVAL_REJECTED, tenant_id=approval.tenant_id, case_id=approval.case_id, correlation_id=corr,
                      source=f"human:{approver_id}", target="sandouk", decision=Decision.BLOCK, severity=Severity.MEDIUM,
                      summary=f"{approver_id} rejected {fmt_tnd(approval.amount_millimes)} for {approval.product_name}",
                      payload={"approval_id": approval_id, "approver_id": approver_id})
        async with self._locks[approval.case_id]:
            case = self._load(approval.case_id)
            if case.state == JS.AWAITING_APPROVAL:
                case.pending_approval_id = None
                case.confirmed_offer_hash = None
                self._transition(case, JS.CONVERSING, f"approval rejected by {approver_id}", corr)
                self._say(case, "rejected_by_team", corr)
                self._save(case)
        return res

    async def settle(self, payment_id: str, succeed: bool = True) -> PaymentIntent | None:
        p = self.repo.get_payment(payment_id)
        if p is None:
            return None
        async with self._locks[p.case_id]:
            updated = self.engine.settle_pending(payment_id, succeed)
            case = self._load(p.case_id)
            if updated and case.state == JS.PAYMENT_PENDING:
                corr = new_id("cor")
                outcome = self._apply_payment(case, updated, None, corr)
                self._finish_payment(case, outcome, corr)
            return updated

    async def reopen(self, case_id: str, by_human: str) -> CaseFile:
        """Only a human takes a case out of BLOCKED. Audited like everything else."""
        async with self._locks[case_id]:
            case = self._load(case_id)
            if case.state == JS.BLOCKED:
                old = case.state
                case.state = JS.CONVERSING
                self.bus.emit(ET.STATE_CHANGED, tenant_id=case.tenant_id, case_id=case_id, source=f"human:{by_human}",
                              summary=f"{by_human} reopened the case ({old.value} -> conversing)",
                              payload={"from": old.value, "to": "conversing", "why": f"human review by {by_human}"})
                self._save(case)
            return case

    # ------------------------------------------------------------------ demo helpers (ops only)
    async def prepare_offer_case(self, tenant_id: str, product_id: str, plan_id: str, method: str = "tok_ok",
                                 channel: Channel = Channel.TEXT, customer_ref: str | None = None,
                                 run_id: str | None = None) -> CaseFile:
        """A case with an offer on the table, without the chat (for demo buttons and tests)."""
        case, _ = await self.open_case(tenant_id, channel, customer_ref=customer_ref, run_id=run_id)
        async with self._locks[case.case_id]:
            case = self._load(case.case_id)
            case.offer = self.tenants.get(tenant_id).build_offer(product_id, plan_id)
            case.product_interest = product_id
            case.payment_method = method
            self._transition(case, JS.OFFER_PROPOSED, "offer prepared by ops", new_id("cor"))
            self._save(case)
        return case

    async def manual_order(self, tenant_id: str, product_id: str, plan_id: str, requested_by: str,
                           method: str = "tok_ok", run_id: str | None = None) -> TurnResult:
        """An order keyed in by a staff member: that person can never approve it."""
        case = await self.prepare_offer_case(tenant_id, product_id, plan_id, method, customer_ref=f"ops:{requested_by}",
                                             run_id=run_id)
        async with self._locks[case.case_id]:
            case = self._load(case.case_id)
            corr = new_id("cor")
            case.payment_attempt = 1
            case.confirmed_offer_hash = case.offer.offer_hash if case.offer else None
            self._transition(case, JS.OFFER_ACCEPTED, f"manual order by {requested_by}", corr)
            outcome = await self._pay(case, corr, requested_by=requested_by)
            return self._finish_payment(case, outcome, corr)
