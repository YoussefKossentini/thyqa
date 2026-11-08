"""Output guard: runs on every reply before the client sees it.

* Price integrity: every amount followed or preceded by a currency must exist in
  the tenant catalog (totals, installments, allowed discounts). Same for
  discount percentages and "free" claims.
* Leaks: canary token, prompt fragments, API keys, card-like numbers (Luhn),
  RIB-like numbers, and Sahbi asking for card data or secrets.
A failing reply is replaced by a deterministic one built from the catalog.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..money import fmt_tnd
from ..schemas import Lang, Offer
from ..tenants import TenantPack

CUR = r"(?:tnd|dt|dinars?|d\.t\.?|د\.ت|دينار|دنانير|millimes?|مليم)"
NUM = r"\d[\d\u00a0\u202f .,]*\d|\d"
MONEY_AFTER = re.compile(rf"(?P<num>{NUM})\s*(?P<cur>{CUR})(?![a-z])", re.IGNORECASE)
MONEY_BEFORE = re.compile(rf"(?<![a-z])(?P<cur>{CUR})\s*(?P<num>{NUM})(?![\da-z])", re.IGNORECASE)
PERCENT = re.compile(r"(?<!\d)(\d{1,3})\s?%")
DISCOUNT_WORDS = re.compile(r"remise|r[ée]duction|discount|\boff\b|promo|rabais|solde|ta5fidh|takhfidh|ta5fid|takhfid|تخفيض|خصم|ريميز", re.IGNORECASE)
HALF_PRICE = re.compile(r"half price|moiti[ée] prix|demi[- ]tarif|nos (el )?soum|نص السوم", re.IGNORECASE)
FREE_CLAIM = re.compile(r"\b(for free|free of charge|it'?s free|is free|c'est gratuit|gratuit[es]?|offert[es]?|b ?blech|bla flous|majj?ani)\b|مجان|ببلاش", re.IGNORECASE)
ASKS_SECRETS = re.compile(r"\b(cvv|cvc|code pin|ton pin|votre pin|mot de passe|password|num[ée]ro de (ta |votre )?carte|card number|code secret|code confidentiel)\b", re.IGNORECASE)
KEY_PATTERNS = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{30,}|gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
CARD_LIKE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
RIB_LIKE = re.compile(r"(?<!\d)\d{20}(?!\d)")
SENTENCE = re.compile(r"(?<=[.!?؟])\s+")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def amount_candidates(num: str, cur: str) -> set[int]:
    """All plausible millime values for a written amount ('1,500' may be 1500 or 1.5 TND)."""
    s = re.sub(r"[\s\u00a0\u202f]", "", num)
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return set()
    if cur.lower().startswith("mill") or cur == "مليم":
        digits = re.sub(r"[.,]", "", s)
        return {int(digits)} if digits else set()
    out: set[int] = set()
    digits = re.sub(r"[.,]", "", s)
    if digits:
        out.add(int(digits) * 1000)                       # separators are thousands
    m = re.fullmatch(r"(.*?)[.,](\d{1,3})", s)
    if m:                                                  # last separator is the decimal mark
        whole = re.sub(r"[.,]", "", m.group(1)) or "0"
        out.add(int(whole) * 1000 + int(m.group(2).ljust(3, "0")))
    return out


@dataclass
class OutputVerdict:
    ok: bool
    text: str
    reasons: list[str] = field(default_factory=list)
    rewritten: bool = False
    leak: bool = False
    found_amounts: list[str] = field(default_factory=list)


class OutputGuard:
    def __init__(self, canary: str, prompt_fragments: list[str] | None = None, max_sentences: int = 2):
        self.canary = canary.lower()
        self.fragments = [f.lower() for f in (prompt_fragments or [])]
        self.max_sentences = max_sentences

    def check(self, text: str, tenant: TenantPack, offer: Offer | None, lang: Lang) -> OutputVerdict:
        reasons: list[str] = []
        low = text.lower()
        leak = False
        if self.canary and self.canary in low:
            reasons.append("canary_leak")
            leak = True
        if any(f in low for f in self.fragments):
            reasons.append("prompt_leak")
            leak = True
        if KEY_PATTERNS.search(text):
            reasons.append("secret_leak")
            leak = True
        for m in CARD_LIKE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                reasons.append("card_number")
                leak = True
                break
        if RIB_LIKE.search(text):
            reasons.append("rib_number")
            leak = True
        if ASKS_SECRETS.search(text):
            reasons.append("asks_for_secrets")

        allowed = tenant.allowed_amounts()
        found: list[str] = []
        for rx in (MONEY_AFTER, MONEY_BEFORE):
            for m in rx.finditer(text):
                found.append(m.group(0))
                cands = amount_candidates(m.group("num"), m.group("cur"))
                if cands and not (cands & allowed):
                    reasons.append(f"price_not_in_catalog:{m.group(0).strip()}")
        allowed_pct = tenant.allowed_discount_percents()
        for m in PERCENT.finditer(text):
            window = text[max(0, m.start() - 30): m.end() + 30]
            if DISCOUNT_WORDS.search(window) and int(m.group(1)) not in allowed_pct:
                reasons.append(f"discount_not_allowed:{m.group(1)}%")
        if HALF_PRICE.search(text) and 50 not in allowed_pct:
            reasons.append("discount_not_allowed:half_price")
        if FREE_CLAIM.search(text):
            reasons.append("free_claim")

        if reasons:
            return OutputVerdict(ok=False, text=safe_reply(tenant, offer, lang), reasons=reasons, rewritten=True,
                                 leak=leak, found_amounts=found)
        trimmed = " ".join(SENTENCE.split(text.strip())[: self.max_sentences])
        return OutputVerdict(ok=True, text=trimmed, found_amounts=found)


def safe_reply(tenant: TenantPack, offer: Offer | None, lang: Lang) -> str:
    """Deterministic reply from the catalog. Must itself pass the guard (tested)."""
    if offer is not None:
        name, total, n, first = offer.product_name, offer.total_millimes, offer.installments, offer.due_now_millimes
    else:
        prod = tenant.product(tenant.default_product)
        if prod is None:
            raise ValueError("tenant has no default product")
        inst = tenant.installment_plans(prod.product_id)
        name, total = prod.name, prod.price_millimes
        n = inst[-1].installments if inst else 1
        first = tenant.price_for(prod.product_id, inst[-1].plan_id)[1][0] if inst else total
    if lang == Lang.FR:
        plan = f", payable en {n} fois ({fmt_tnd(first, 'derja')} maintenant)" if n > 1 else ""
        return f"Pour être précis : {name} coûte {fmt_tnd(total, 'derja')}{plan}. Je ne peux pas accorder de remise hors des offres officielles."
    if lang == Lang.EN:
        plan = f", or {n} installments ({fmt_tnd(first, 'derja')} now)" if n > 1 else ""
        return f"To be precise: {name} costs {fmt_tnd(total, 'derja')}{plan}. I can't give discounts outside the official offers."
    plan = f", w tnajjem tkhallas 3la {n} marrat ({fmt_tnd(first, 'derja')} tawa)" if n > 1 else ""
    return f"Bech nkoun d9i9 m3ak: soum {name} {fmt_tnd(total, 'derja')}{plan}. Ma n9edrch na3ti remise kharej el offres el rasmiya."
