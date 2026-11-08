"""Input guard: rules/regex in Derja (Arabizi + Arabic script), French and English,
then structural checks. Flagged text is quarantined and never reaches Sahbi.

This is one signal among several. The guarantee does not depend on it: agents
have no tool that moves money, and the payment engine checks a signed
authorization (see bouab/core.py, pay/engine.py).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..schemas import Lang

MAX_CHARS = 600

_INVISIBLE = set("\u200b\u200c\u2060\ufeff\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_DROP = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\ufeff\u00ad\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"), None)
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "ɡ": "g", "ո": "n", "ս": "u", "ᴏ": "o", "ı": "i", "ⅰ": "i", "ο": "o", "α": "a", "ε": "e",
    "ρ": "p", "τ": "t", "ν": "v", "κ": "k", "ι": "i",
})
_AR_DIACRITICS = re.compile(r"[ً-ْٰـ]")
_AR_NORMAL = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"})
_SPACED_LETTERS = re.compile(r"\b(?:\w[ .\-_*]){3,}\w\b")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = t.translate(_DROP).translate(_HOMOGLYPHS).lower()
    t = _AR_DIACRITICS.sub("", t).translate(_AR_NORMAL)
    t = re.sub(r"([^\W\d_])\1{2,}", r"\1", t)                         # ignooore -> ignore (letters only)
    t = _SPACED_LETTERS.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), t)  # i.g.n.o.r.e -> ignore
    return re.sub(r"\s+", " ", t).strip()


W = r"[^.!?\n]"  # "within the same sentence"

# (code, pattern) - any match flags the message
HARD_RULES: list[tuple[str, str]] = [
    # English
    ("ignore_instructions", rf"\b(ignore|disregard|forget|override|bypass|skip)\b{W}{{0,40}}\b(instructions?|rules|prompts?|guidelines|polic(y|ies)|directives|system message)\b"),
    ("role_override", r"\b(you are now|from now on,? you are|pretend (to be|you are)|roleplay as|act as (an? |the )?(admin|developer|system|unrestricted|jailbroken|dan))\b"),
    ("jailbreak", r"\b(jailbreak|developer mode|dan mode|do anything now|god mode|unrestricted mode|no restrictions)\b"),
    ("prompt_leak", rf"\b(reveal|show|print|repeat|display|leak|tell me|give me|what (is|are))\b{W}{{0,30}}\b(system prompt|your prompt|your instructions|hidden instructions|initial instructions|your rules|api key|secret key|password)\b"),
    ("price_override", rf"\b(set|change|make|put|update)\b{W}{{0,25}}\b(price|amount|cost|total)\b{W}{{0,20}}\b(0|zero|free|1 ?(tnd|dt))\b"),
    ("discount_100", r"\b100 ?% ?(off|discount)|\b(discount|reduction) of 100 ?%"),
    ("approval_forgery", rf"\b(approve|authori[sz]e|validate)\b{W}{{0,25}}\b(payment|transaction|refund|transfer)\b{W}{{0,25}}\b(without|no|skip|bypass)\b"),
    ("fake_authority", r"\b(i am|i'm|this is|ena|je suis)\s+(the\s+|l'|el\s+|le\s+)?(admin|administrator|administrateur|bouab|security team|syst[eè]me|system|developer of (this|the) (bot|system))\b"),
    ("delimiters", r"<\|?(im_start|im_end|system|endoftext|assistant)\|?>|\[/?(inst|sys)\]|(^|\n)\s*(system|assistant|developer)\s*:|#{3,}\s*(system|instructions?)"),
    ("json_role", r"\"role\"\s*:\s*\"(system|assistant|developer)\""),
    # French
    ("ignore_instructions_fr", rf"\b(ignore[sz]?|oublie[sz]?|ne tiens pas compte|ne tenez pas compte|contourne[sz]?)\b{W}{{0,40}}\b(instructions?|consignes?|r[eè]gles?|prompt|directives?)\b"),
    ("role_override_fr", r"\b(tu es|vous [eê]tes) (maintenant|d[ée]sormais)\b|\bmode (d[ée]veloppeur|admin|sans restriction)\b"),
    ("prompt_leak_fr", rf"\b(r[ée]v[eè]le|affiche|montre|donne|dis|r[ée]p[eè]te)[sz]?(-moi| moi)?\b{W}{{0,30}}\b(ton prompt|tes instructions|vos instructions|tes consignes|prompt syst[eè]me|cl[ée] api|mot de passe)\b"),
    ("discount_100_fr", rf"\b(remise|r[ée]duction|rabais|promo)\b{W}{{0,12}}\b100 ?%|100 ?% ?(de )?(remise|r[ée]duction|rabais)"),
    ("price_override_fr", rf"\b(mets?|mettez|fixe[sz]?|change[sz]?|passe[sz]?)\b{W}{{0,25}}\b(prix|montant|tarif)\b{W}{{0,20}}\b(0|z[ée]ro|gratuit)\b"),
    ("approval_forgery_fr", rf"\b(valide[sz]?|approuve[sz]?|autorise[sz]?)\b{W}{{0,25}}\b(paiement|transaction|virement)\b{W}{{0,25}}\b(sans|directement)\b"),
    # Derja, Arabizi
    ("ignore_instructions_derja", rf"\b(ensa|insa|nsa|tensa|ensay|ensaw|sayeb|sayyeb|khalli 3lik men|5alli 3lik men)\b{W}{{0,30}}\b(ta3limet|ta3limat|t3limet|ta3limetek|ta3limatek|ta3lim|instructions?|el prompt|prompt|9wanin|qawanin|9awa3ed|consignes)\b"),
    ("discount_100_derja", rf"\b(a3tini|3tini|a3teni|a3tih|a3tina|7ot|7ott|hot)\b{W}{{0,25}}\b(remise|ta5fidh|takhfidh|ta5fid|takhfid|reduction|r[ée]duction|promo)\b{W}{{0,12}}\b100\b|\b(remise|ta5fidh|takhfidh)\s*(b\s*)?100\b"),
    ("prompt_leak_derja", rf"\b(warrini|warini|wariny|ourini|9olli|9oulli|9ouli|9olna|kolli)\b{W}{{0,30}}\b(el prompt|prompt|ta3limet|ta3limetek|ta3limatek|instructions|el system|el sir|sirr|mot de passe|password)\b"),
    ("role_override_derja", rf"\b(walli|wallit|enti tawa|inti tawa|enta tawa|tawa enti|tawa inti)\b{W}{{0,25}}\b(admin|system|syst[eè]me|developer|d[ée]veloppeur|bouab|mode)\b"),
    ("price_override_derja", rf"\b(5alli|khalli|7ot|7ott|hot|rodd|radd)\b{W}{{0,20}}\b(el soum|soum|el prix|prix|el montant|montant)\b{W}{{0,20}}\b(0|sfer|sifr|zero|z[ée]ro|b ?blech|bla flous|gratuit)\b"),
    ("approval_forgery_derja", rf"\b(valide|validi|approuvi|sadde9|sadda9|3addi|3addih)\b{W}{{0,25}}\b(el paiement|paiement|el 5las|el khlas|5las|khlas)\b{W}{{0,25}}\b(men ghir|bla|direct)\b"),
    # Arabic script
    ("ignore_instructions_ar", rf"(تجاهل|انسي|انسى|انس)\s*{W}{{0,30}}(التعليمات|تعليمات|القواعد|قواعد|الاوامر)"),
    ("discount_100_ar", rf"(تخفيض|خصم|ريميز){W}{{0,12}}100|100{W}{{0,6}}(تخفيض|خصم)"),
    ("prompt_leak_ar", rf"(اكشف|وريني|اعطيني|قلي|قولي){W}{{0,30}}(التعليمات|تعليماتك|البرومبت|النظام|كلمة السر)"),
]
_HARD = [(code, re.compile(p, re.IGNORECASE | re.MULTILINE)) for code, p in HARD_RULES]

_BASE64 = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_MARKUP = re.compile(r"```|<script|</?(system|prompt|instructions?)>|\{\s*\"[a-z_]+\"\s*:", re.IGNORECASE)
_LATIN = re.compile(r"[a-zA-Z]")
_CYRGREEK = re.compile(r"[Ͱ-ϿЀ-ӿ]")


@dataclass
class GuardVerdict:
    flagged: bool
    reasons: list[str] = field(default_factory=list)
    structural_score: int = 0
    normalized: str = ""
    lang: Lang = Lang.DERJA


def guess_lang(text: str) -> Lang:
    if re.search(r"[\u0600-ۿ]", text):
        return Lang.AR
    t = f" {text.lower()} "
    fr = sum(w in t for w in (" je ", " vous ", " est ", " pour ", " avec ", " c'est", " le ", " la ", " les ", " une ", " combien", " prix", "réduction", "merci"))
    en = sum(w in t for w in (" the ", " you ", " is ", " please", " how ", " what ", " price", " give ", " can ", " i'm ", " i want"))
    derja = sum(w in t for w in (" 3", "9a", "7a", " chnowa", " nheb", " n7eb", " ghali", " barcha", " soum", " behi", " ey ", " ena ", " tawa", " fama", " famma", "kadech", "9adeh"))
    best = max((derja, Lang.DERJA), (fr, Lang.FR), (en, Lang.EN), key=lambda x: x[0])
    return best[1] if best[0] > 0 else Lang.DERJA


class InputGuard:
    def __init__(self, max_chars: int = MAX_CHARS):
        self.max_chars = max_chars

    def check(self, text: str) -> GuardVerdict:
        reasons: list[str] = []
        structural = 0
        if len(text) > self.max_chars:
            reasons.append("too_long")
        if sum(ch in _INVISIBLE for ch in text) >= 1:
            structural += 3
            reasons.append("invisible_chars")
        if any(_LATIN.search(w) and _CYRGREEK.search(w) for w in text.split()):
            structural += 3
            reasons.append("homoglyphs")
        if text.count("\n") > 8:
            structural += 2
            reasons.append("many_lines")
        if _BASE64.search(text):
            structural += 3
            reasons.append("encoded_payload")
        if _MARKUP.search(text):
            structural += 2
            reasons.append("markup")
        norm = normalize(text)
        for code, rx in _HARD:
            if rx.search(norm) or rx.search(text):
                reasons.append(code)
        hard = [r for r in reasons if r not in ("invisible_chars", "homoglyphs", "many_lines", "encoded_payload", "markup")]
        flagged = bool(hard) or structural >= 3
        return GuardVerdict(flagged=flagged, reasons=reasons, structural_score=structural, normalized=norm, lang=guess_lang(text))


CANNED_REPLY = {
    Lang.DERJA: "Smahli, ma nnajjamch nemchi fel 7aja hadhi. Nkamlou 3al formation?",
    Lang.AR: "Smahli, ma nnajjamch nemchi fel 7aja hadhi. Nkamlou 3al formation?",
    Lang.FR: "Désolé, je ne peux pas traiter cette demande. On continue sur la formation ?",
    Lang.EN: "Sorry, I can't help with that request. Shall we continue with the course?",
}
