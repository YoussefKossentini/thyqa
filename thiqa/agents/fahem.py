"""Fahem, Customer Intelligence. LLM -> strict JSON (enums, scores). Mock fallback is lexicon-based."""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..bouab.input_guard import guess_lang
from ..llm import LLMGateway, mock_forced
from ..schemas import AIMode, CaseFile, FahemAnalysis, Intent, Lang, Objection, Persona, Radar
from .lexicon import detect, is_explicit_confirmation
from .prompts import FAHEM_SYSTEM

OBJ_TAGS = {
    "obj_price": Objection.PRICE, "obj_trust": Objection.TRUST, "obj_time": Objection.TIME,
    "obj_relevance": Objection.RELEVANCE, "obj_comprehension": Objection.COMPREHENSION, "obj_payment": Objection.PAYMENT_METHOD,
}


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def mock_analysis(texts: list[str], prev: FahemAnalysis | None = None) -> FahemAnalysis:
    if not texts:
        return FahemAnalysis(intent=Intent.GREETING, sentiment=0, objections=[], satisfaction="neutral",
                             radar=Radar(price_sensitivity=30, trust=60, urgency=30, comprehension=80, intent=20),
                             persona=Persona.UNKNOWN, lang=Lang.DERJA)
    sigs = [detect(t) for t in texts]
    last = sigs[-1]
    turns_with = lambda tag: sum(1 for s in sigs if tag in s.tags)  # noqa: E731
    objections = [obj for tag, obj in OBJ_TAGS.items() if tag in last.tags]
    if is_explicit_confirmation(texts[-1]):
        intent = Intent.CONFIRM
    elif last.has("decline"):
        intent = Intent.DECLINE
    elif last.has("purchase"):
        intent = Intent.PURCHASE_INTENT
    elif objections:
        intent = Intent.OBJECTION
    elif last.has("price_q"):
        intent = Intent.PRICE_QUESTION
    elif last.has("info", "installments", "discount_ask"):
        intent = Intent.INFO_REQUEST
    elif last.has("greeting"):
        intent = Intent.GREETING
    elif last.has("positive"):
        intent = Intent.INTEREST
    else:
        intent = Intent.INFO_REQUEST
    sentiment = (25 * last.counts.get("positive", 0) - 35 * last.counts.get("negative", 0) - 15 * len(objections)
                 + 25 * (intent in (Intent.PURCHASE_INTENT, Intent.CONFIRM)) - 30 * (intent == Intent.DECLINE))
    sentiment = max(-100, min(100, sentiment))
    satisfaction = "positive" if sentiment > 15 else "negative" if sentiment < -15 else "neutral"
    radar = Radar(
        price_sensitivity=_clamp(25 + 25 * turns_with("obj_price") + 10 * turns_with("price_q") + 10 * turns_with("student")),
        trust=_clamp(65 - 22 * turns_with("obj_trust") + 8 * turns_with("positive")),
        urgency=_clamp(30 + 22 * turns_with("urgency") - 12 * turns_with("obj_time")),
        comprehension=_clamp(80 - 25 * turns_with("obj_comprehension") + 5 * turns_with("info")),
        intent=_clamp(20 + 10 * turns_with("info") + 10 * turns_with("price_q") + 35 * turns_with("purchase")
                      + 8 * turns_with("positive") - 30 * turns_with("decline") + 40 * (intent == Intent.CONFIRM)),
    )
    all_tags = set().union(*(s.tags for s in sigs))
    if "parent" in all_tags:
        persona = Persona.PARENT
    elif "student" in all_tags and "obj_price" in all_tags:
        persona = Persona.BROKE_STUDENT
    elif "student" in all_tags:
        persona = Persona.STUDENT
    elif "pro" in all_tags or ("obj_time" in all_tags and "urgency" in all_tags):
        persona = Persona.RUSHED_PRO
    else:
        persona = prev.persona if prev else Persona.UNKNOWN
    return FahemAnalysis(intent=intent, sentiment=sentiment, objections=objections, satisfaction=satisfaction,
                         radar=radar, persona=persona, lang=guess_lang(texts[-1]))


def _merge(llm: dict[str, Any], fallback: FahemAnalysis) -> FahemAnalysis:
    """Keep only well-typed LLM fields; anything odd falls back to the mock value."""
    base = fallback.model_dump(mode="json")
    out = dict(base)
    for key in ("intent", "satisfaction", "persona", "lang"):
        if isinstance(llm.get(key), str):
            out[key] = llm[key].strip().lower()
    if isinstance(llm.get("sentiment"), (int, float)):
        out["sentiment"] = int(max(-100, min(100, llm["sentiment"])))
    if isinstance(llm.get("objections"), list):
        out["objections"] = [o for o in (str(x).lower() for x in llm["objections"]) if o in Objection._value2member_map_][:6]
    if isinstance(llm.get("radar"), dict):
        out["radar"] = {k: _clamp(llm["radar"].get(k, base["radar"][k])) if isinstance(llm["radar"].get(k), (int, float))
                        else base["radar"][k] for k in base["radar"]}
    try:
        return FahemAnalysis.model_validate(out)
    except ValidationError:
        return fallback


class Fahem:
    def __init__(self, llm: LLMGateway):
        self.llm = llm

    async def analyze(self, case: CaseFile) -> tuple[FahemAnalysis, AIMode]:
        texts = [t.text for t in case.turns if t.role == "client" and not t.withheld]
        fallback = mock_analysis(texts, case.intelligence)
        if not texts or self.llm.mode == "mock" or mock_forced():
            return fallback, AIMode.MOCK
        transcript = "\n".join(f"CLIENT: {t}" for t in texts[-6:])
        res = await self.llm.complete_json("fahem", FAHEM_SYSTEM, [{"role": "user", "content": transcript}],
                                           context_key=case.tenant_id, temperature=0.1, max_tokens=220)
        if res is None:
            return fallback, AIMode.MOCK
        return _merge(res.data, fallback), res.mode
