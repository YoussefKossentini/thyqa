"""Sahbi, Voice Sales. LLM in Derja with a deterministic template fallback (MOCK).

Sahbi only emits a typed SahbiReply. It never computes an amount: when it wants
to sell, it names a product_id and a plan_id and the code builds the Offer.
"""
from __future__ import annotations

import hashlib
import re

from pydantic import ValidationError

from ..bouab.input_guard import guess_lang
from ..llm import LLMGateway, mock_forced
from ..money import fmt_tnd
from ..schemas import (
    AIMode,
    CaseFile,
    JourneyState,
    Lang,
    Objection,
    ObjectionStrategy,
    Persona,
    SahbiAction,
    SahbiReply,
    ScriptVersion,
)
from ..tenants import TenantPack
from .lexicon import detect
from .prompts import sahbi_system

OS = ObjectionStrategy

# {name} {price} {inst} {n} {duration} {schedule} {h1} {h2} {h3} {names} {code} {pct}
T: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "derja": ["Ahla bik! 3andna {names}. Chnowa yhemmek akthar?"],
        "fr": ["Bienvenue ! Nous avons {names}. Qu'est-ce qui vous intéresse le plus ?"],
        "en": ["Welcome! We have {names}. Which one interests you most?"],
    },
    "pitch": {
        "derja": ["{name}: {duration}, tet3allem {h1} w {h2}, w fel le5er {h3}.", "{name} fih {h1} w {h2}, {duration} ({schedule})."],
        "fr": ["{name} : {duration}, avec {h1} et {h2}, et à la fin {h3}."],
        "en": ["{name}: {duration} with {h1} and {h2}, and {h3} at the end."],
    },
    "monthly": {
        "derja": [" Soumha {inst} kol chhar ({n} marrat)."],
        "fr": [" C'est {inst} par mois ({n} échéances)."],
        "en": [" It's {inst} a month ({n} installments)."],
    },
    "cta": {
        "derja": [" T7eb nhadhrolek el offre?", " T7eb ta3ref akthar?"],
        "fr": [" Je vous prépare l'offre ?"],
        "en": [" Shall I prepare the offer?"],
    },
    "price_full": {
        "derja": ["Soum {name} {price} ({duration})."],
        "fr": ["{name} coûte {price} ({duration})."],
        "en": ["{name} costs {price} ({duration})."],
    },
    "price_monthly": {
        "derja": ["{name} b {inst} kol chhar ({n} marrat), walla {price} mara wa7da."],
        "fr": ["{name} : {inst} par mois en {n} fois, ou {price} en une fois."],
        "en": ["{name}: {inst} a month over {n} months, or {price} at once."],
    },
    "obj_price_value": {
        "derja": ["Na3ref elli {price} yetsamma barcha, ama fih {h1} w {h2}. W tnajjem tkhallas 3la {n} marrat ({inst} kol chhar)."],
        "fr": ["Je comprends, {price} c'est un budget, mais vous avez {h1} et {h2}. Vous pouvez aussi payer en {n} fois ({inst} par mois)."],
        "en": ["I get it, {price} is a budget, but you get {h1} and {h2}. You can also pay in {n} installments ({inst} a month)."],
    },
    "obj_price_value_only": {
        "derja": ["Na3ref elli {price} yetsamma barcha, ama fih {h1}, {h2} w {h3}."],
        "fr": ["Je comprends, mais pour {price} vous avez {h1}, {h2} et {h3}."],
        "en": ["I understand, but for {price} you get {h1}, {h2} and {h3}."],
    },
    "obj_price_installments": {
        "derja": ["Fhemtek. Tnajjem tkhallas {name} 3la {n} marrat: {inst} tawa w {inst} kol chhar. Nhadhrolek el offre?"],
        "fr": ["Je comprends. Vous pouvez payer {name} en {n} fois : {inst} maintenant puis {inst} par mois. Je prépare l'offre ?"],
        "en": ["Got it. You can pay {name} in {n} installments: {inst} now, then {inst} a month. Shall I prepare it?"],
    },
    "obj_trust_value": {
        "derja": ["{name} fih {h1} w {h3}, w kol chay wadha7 9bal ma tkhallas."],
        "fr": ["{name} inclut {h1} et {h3}, et tout est clair avant de payer."],
        "en": ["{name} includes {h1} and {h3}, and everything is clear before you pay."],
    },
    "obj_trust_program": {
        "derja": ["Normal t7eb tet2akked. Nab3athlek el programme kamel w tnajjem tehder m3a formateur 9bal ma tkhallas."],
        "fr": ["C'est normal de vérifier. Je vous envoie le programme complet et vous pouvez parler à un formateur avant de payer."],
        "en": ["Fair enough. I'll send you the full program and you can talk to a trainer before paying."],
    },
    "obj_time": {
        "derja": ["{name}: {schedule}, w {duration} bark."],
        "fr": ["{name} : {schedule}, sur {duration}."],
        "en": ["{name}: {schedule}, over {duration}."],
    },
    "obj_relevance": {
        "derja": ["{name} ya3tik {h1} w {h2}, tnajjem testa3melhom fel 5edma direct."],
        "fr": ["{name} vous apporte {h1} et {h2}, utilisables tout de suite au travail."],
        "en": ["{name} gives you {h1} and {h2} you can use at work right away."],
    },
    "obj_comprehension": {
        "derja": ["B kelma wa7da: {name} t3allmek {h1} b {h2}, step by step."],
        "fr": ["En une phrase : {name} vous apprend {h1} avec {h2}, pas à pas."],
        "en": ["In one sentence: {name} teaches you {h1} with {h2}, step by step."],
    },
    "obj_payment": {
        "derja": ["Tnajjem tkhallas b carte (test) walla b virement (simulé), w zeda 3la marrat ken t7eb."],
        "fr": ["Vous pouvez payer par carte (test) ou par virement (simulé), et en plusieurs fois si vous voulez."],
        "en": ["You can pay by card (test) or bank transfer (simulated), in installments if you like."],
    },
    "student_code": {
        "derja": ["Ken enti étudiant, 3andek el code {code}: {pct}% remise 3al {name}."],
        "fr": ["Si vous êtes étudiant, le code {code} donne {pct}% de remise sur {name}."],
        "en": ["If you're a student, code {code} gives {pct}% off {name}."],
    },
    "offer": {
        "derja": ["Mriguel! Hadhi el offre: {name}, {plan_text}. Ken mwafe9, ekteb 'nconfirmi' walla enzel 3al bouton."],
        "fr": ["Parfait ! Voici l'offre : {name}, {plan_text}. Si c'est bon, écrivez « je confirme » ou cliquez sur le bouton."],
        "en": ["Great! Here's the offer: {name}, {plan_text}. If it works for you, type 'I confirm' or press the button."],
    },
    "decline": {
        "derja": ["Ma famma 7atta mochkla. Ken tbaddel ra2yek, ena houni."],
        "fr": ["Aucun souci. Si vous changez d'avis, je suis là."],
        "en": ["No problem. If you change your mind, I'm here."],
    },
    "after_paid": {
        "derja": ["3aychek! Ken 3andek ay sou2el 3al formation, ena houni."],
        "fr": ["Merci ! Pour toute question sur la formation, je suis là."],
        "en": ["Thanks! Any question about the course, I'm here."],
    },
    "fallback": {
        "derja": ["Fhemtek. T7eb nfasserlek {name} walla ta3ref el soum?"],
        "fr": ["D'accord. Je vous présente {name} ou vous voulez le prix ?"],
        "en": ["Sure. Want me to walk you through {name}, or the price?"],
    },
}

PLAN_TEXT = {
    "derja": ("{price} mara wa7da", "{n} marrat ({inst} tawa, total {price})"),
    "fr": ("{price} en une fois", "{n} échéances ({inst} maintenant, total {price})"),
    "en": ("{price} at once", "{n} installments ({inst} now, {price} in total)"),
}

FULL_WORDS = re.compile(r"mara wa7da|marra we7da|en une fois|comptant|cash|full|complet|kamel", re.IGNORECASE)


def _lang_key(lang: Lang) -> str:
    return {Lang.FR: "fr", Lang.EN: "en"}.get(lang, "derja")


def _pick(key: str, lang: str, seed: str) -> str:
    options = T[key].get(lang) or T[key]["derja"]
    return options[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(options)]


def product_facts(tenant: TenantPack, product_id: str) -> dict[str, str | int]:
    prod = tenant.product(product_id) or tenant.product(tenant.default_product)
    if prod is None:
        raise ValueError("tenant has no default product")
    inst_plans = tenant.installment_plans(prod.product_id)
    plan = inst_plans[-1] if inst_plans else None
    first = tenant.price_for(prod.product_id, plan.plan_id)[1][0] if plan else prod.price_millimes
    h = (prod.highlights + ["", "", ""])[:3]
    names = [p.name for p in tenant.catalog[:3]]
    return {"product_id": prod.product_id, "name": prod.name, "price": fmt_tnd(prod.price_millimes, "derja"),
            "inst": fmt_tnd(first, "derja"), "n": plan.installments if plan else 1, "duration": prod.duration,
            "schedule": prod.schedule, "h1": h[0], "h2": h[1], "h3": h[2],
            "names": ", ".join(names[:-1]) + (" w " if len(names) > 1 else "") + names[-1],
            "installment_plan": plan.plan_id if plan else "", "full_plan": prod.plans[0]}


def mock_reply(case: CaseFile, tenant: TenantPack, script: ScriptVersion) -> SahbiReply:
    client_turns = [t.text for t in case.turns if t.role == "client" and not t.withheld]
    last = client_turns[-1] if client_turns else ""
    sig = detect(last)
    lang = _lang_key(guess_lang(last) if last else Lang.DERJA)
    seed = f"{case.customer_ref}:{len(client_turns)}"
    f = product_facts(tenant, case.product_interest or tenant.default_product)
    prior_price_obj = sum(1 for t in client_turns[:-1] if "obj_price" in detect(t).tags)
    persona = case.intelligence.persona if case.intelligence else Persona.UNKNOWN
    strat = script.objection_strategies

    def say(key: str, **extra) -> str:
        return _pick(key, lang, seed + key).format(**{**f, **extra})

    if case.state == JourneyState.PAID:
        return SahbiReply(text=say("after_paid"))
    if sig.has("decline"):
        return SahbiReply(text=say("decline"), action=SahbiAction.CLOSE)

    # Buying signal -> typed offer request (the code computes the money)
    if sig.has("purchase") or (sig.has("installments") and sig.has("positive")):
        wants_full = bool(FULL_WORDS.search(last)) or "full_payment_only" in case.restrictions
        use_inst = bool(f["installment_plan"]) and not wants_full and (
            sig.has("installments") or prior_price_obj > 0 or Objection.PRICE in case.objections_seen
            or script.lead_with_monthly_price)
        plan_id = str(f["installment_plan"] if use_inst else f["full_plan"])
        code = None
        is_student = persona in (Persona.STUDENT, Persona.BROKE_STUDENT) or sig.has("student")
        if is_student and (sig.has("discount_ask") or OS.STUDENT_DISCOUNT in strat.values()):
            dc = next((d for d in tenant.discount_codes if f["product_id"] in d.applies_to), None)
            code = dc.code if dc else None
        total, schedule, _ = tenant.price_for(str(f["product_id"]), plan_id, code)
        tmpl_full, tmpl_inst = PLAN_TEXT[lang]
        plan_text = (tmpl_inst if len(schedule) > 1 else tmpl_full).format(
            n=len(schedule), inst=fmt_tnd(schedule[0], "derja"), price=fmt_tnd(total, "derja"))
        return SahbiReply(text=say("offer", plan_text=plan_text), action=SahbiAction.PROPOSE_OFFER,
                          product_id=str(f["product_id"]), plan_id=plan_id, discount_code=code)

    # Student discount question
    if sig.has("discount_ask") and tenant.discount_codes:
        dc = next((d for d in tenant.discount_codes if f["product_id"] in d.applies_to), None)
        if dc:
            return SahbiReply(text=say("student_code", code=dc.code, pct=dc.percent))

    # Objections, in priority order, handled by the active script
    has_inst = bool(f["installment_plan"])
    if sig.has("obj_price"):
        s = strat.get(Objection.PRICE, OS.VALUE_FIRST)
        if has_inst and (s == OS.INSTALLMENTS_FIRST or prior_price_obj > 0):
            return SahbiReply(text=say("obj_price_installments"))
        return SahbiReply(text=say("obj_price_value" if has_inst else "obj_price_value_only"))
    if sig.has("obj_trust"):
        s = strat.get(Objection.TRUST, OS.VALUE_FIRST)
        return SahbiReply(text=say("obj_trust_program" if s == OS.SHOW_PROGRAM else "obj_trust_value"))
    if sig.has("obj_time"):
        return SahbiReply(text=say("obj_time"))
    if sig.has("obj_relevance"):
        return SahbiReply(text=say("obj_relevance"))
    if sig.has("obj_comprehension"):
        return SahbiReply(text=say("obj_comprehension"))
    if sig.has("obj_payment"):
        return SahbiReply(text=say("obj_payment"))

    if sig.has("price_q"):
        key = "price_monthly" if (script.lead_with_monthly_price and has_inst) else "price_full"
        return SahbiReply(text=say(key))
    if sig.has("greeting") and len(client_turns) <= 1 and not sig.has("info"):
        return SahbiReply(text=say("greeting"))
    if sig.has("info", "greeting", "positive", "installments"):
        text = say("pitch")
        if script.lead_with_monthly_price and has_inst:
            text += say("monthly")
        return SahbiReply(text=text + say("cta"))
    return SahbiReply(text=say("fallback"))


def opening_line(tenant: TenantPack, script: ScriptVersion, lang: Lang = Lang.DERJA) -> str:
    key = _lang_key(lang)
    disclosure = tenant.disclosure.get(key) or next(iter(tenant.disclosure.values()))
    question = {"derja": " Chnowa t7eb ta3ref?", "fr": " Que puis-je faire pour vous ?", "en": " How can I help?"}[key]
    if script.opening == "question_first":
        question = {"derja": " Enti tnajjem t9olli chnowa te5dem walla ta9ra?", "fr": " Vous étudiez ou vous travaillez ?",
                    "en": " Are you studying or working?"}[key]
    return disclosure + question


class Sahbi:
    def __init__(self, llm: LLMGateway, canary: str):
        self.llm = llm
        self.canary = canary

    async def reply(self, case: CaseFile, tenant: TenantPack, script: ScriptVersion) -> tuple[SahbiReply, AIMode]:
        fallback = mock_reply(case, tenant, script)
        if self.llm.mode == "mock" or mock_forced():
            return fallback, AIMode.MOCK
        msgs = []
        for t in case.turns[-10:]:
            if t.role == "client":
                msgs.append({"role": "user", "content": "[withheld by Fouchika]" if t.withheld else t.text})
            elif t.role == "sahbi":
                msgs.append({"role": "assistant", "content": t.text})
        if not msgs or msgs[-1]["role"] != "user":
            return fallback, AIMode.MOCK
        system = sahbi_system(tenant, script, case, self.canary)
        res = await self.llm.complete_json("sahbi", system, msgs,
                                           context_key=f"{tenant.tenant_id}:v{script.version}:{case.state.value}")
        if res is None:
            return fallback, AIMode.MOCK
        try:
            data = {k: res.data.get(k) for k in ("text", "action", "product_id", "plan_id", "discount_code")}
            data["action"] = (data.get("action") or "none").lower()
            data["text"] = str(data.get("text") or "").strip()[:480]
            reply = SahbiReply.model_validate({k: v for k, v in data.items() if v is not None})
        except (ValidationError, AttributeError):
            return fallback, AIMode.MOCK
        if reply.action == SahbiAction.PROPOSE_OFFER and (not reply.product_id or not tenant.product(reply.product_id)):
            reply = reply.model_copy(update={"action": SahbiAction.NONE, "product_id": None, "plan_id": None})
        return reply, res.mode
