"""Derja / French / English / Arabic keyword lexicon.

Used by the MOCK versions of Fahem and Sahbi (no LLM, deterministic) and by the
Zbayen simulator. It is also the fallback when every LLM provider is down.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

LEX: dict[str, list[str]] = {
    "greeting": ["aslema", "asslema", "ahla", "ahlan", "salam", "salut", "bonjour", "bonsoir", "hello", "hi", "hey", "عسلامة", "أهلا", "السلام"],
    "info": ["chnowa", "chneya", "programme", "program", "contenu", "duree", "duration", "modalites", "details", "detail", "info",
             "formation", "course", "explique moi", "tell me", "ta3ref", "na3ref", "fasserli", "شنوة", "برنامج", "comment ca marche"],
    "price_q": ["9adeh", "9addeh", "9adech", "kadech", "kaddech", "bkadech", "b9adech", "b9addeh", "soum", "soumha", "prix", "combien",
                "tarif", "price", "how much", "cost", "سوم", "قداش", "بقداش", "السعر"],
    "obj_price": ["ghali", "ghalia", "ghalya", "cher", "chere", "expensive", "trop", "ma3andich flous", "ma 3andich flous",
                  "ma3andich el flous", "budget", "afford", "flous barcha", "غالي", "ما عنديش فلوس"],
    "obj_trust": ["arnaque", "scam", "nthi9", "thi9a", "confiance", "fiable", "serieux", "legit", "trust", "reconnu", "madhmoun",
                  "mdhmoun", "certifie", "ثقة", "مضمون", "نصبة", "avis", "reviews", "garantie"],
    "obj_time": ["wa9t", "wakt", "temps", "busy", "occupe", "horaire", "schedule", "ma3andich wa9t", "pas le temps", "no time",
                 "وقت", "planning"],
    "obj_relevance": ["chnowa nestfed", "ch nestfed", "a quoi ca sert", "utile", "useful", "worth it", "ma yhemnich", "pourquoi",
                      "why should", "ما يهمنيش", "nest7a9ha", "nesta79ha"],
    "obj_comprehension": ["ma fhemtch", "ma fhemt", "chnowa ya3ni", "c'est quoi", "explique", "explain", "what does", "fhemni",
                          "pas compris", "ما فهمتش", "kifech"],
    "obj_payment": ["carte", "card", "virement", "transfer", "edinar", "e-dinar", "flouci", "d17", "cash", "espece", "كارطة"],
    "purchase": ["nheb nchri", "n7eb nchri", "nheb nsajjel", "n7eb nsajjel", "nsajjel", "nsajel", "ntsajjel", "nheb netsajjel",
                 "n7eb netsajjel", "inscri", "je veux m'inscrire", "je prends", "i want to buy", "i'll take", "sign me up", "nkhallas",
                 "n5alles", "nkhalles", "n5allas", "reserver", "book", "yezzi nchri", "behi nchri", "ok nchri", "nheb nkhallas",
                 "نحب نسجل", "نحب نشري", "nheb nebda", "nebdew", "let's go", "on y va", "i want it", "je le veux", "nheb el offre"],
    "decline": ["la merci", "le merci", "non merci", "no thanks", "ma nhebch", "ma n7ebch", "mouch tawa", "pas maintenant",
                "not now", "no thank", "ما نحبش", "موش توا", "beslema", "bye", "pas interesse", "not interested"],
    "positive": ["behi", "mriguel", "yeser behi", "top", "genial", "super", "great", "merci", "ya3tik essa7a", "3jebni", "parfait",
                 "perfect", "nice", "يعطيك الصحة", "مريقل", "bravo", "7lowa", "hlowa", "cool"],
    "negative": ["khayeb", "5ayeb", "nul", "bad", "terrible", "y9alla9", "ma3jebnich", "decu", "خايب", "ma7lech", "ennuyeux"],
    "urgency": ["tawa", "fissa3", "urgent", "asap", "rapidement", "ce mois", "had chhar", "lyoum", "today", "vite", "توا", "فيسع",
                "deadline", "bientot"],
    "student": ["etudiant", "etudiante", "9ari", "na9ra", "student", "fac", "universite", "university", "طالب", "nakra", "master",
                "licence"],
    "parent": ["weldi", "benti", "mon fils", "ma fille", "my son", "my daughter", "ولدي", "بنتي", "lwlad", "enfant"],
    "pro": ["5edma", "khedma", "travail", "job", "boss", "entreprise", "company", "manager", "salarie", "nekhdem", "ne5dem", "نخدم"],
    "installments": ["marrat", "tranches", "tranche", "installment", "installments", "par mois", "kol chhar", "mensuel", "x3", "x2",
                     "3 fois", "2 fois", "facilite", "تقسيط", "echeance", "3 marat"],
    "discount_ask": ["remise", "reduction", "promo", "discount", "ta5fidh", "takhfidh", "تخفيض", "code promo"],
}

PRODUCT_HINTS: dict[str, list[str]] = {
    "ai_bootcamp": ["bootcamp", "ai engineer", "engineer", "ingenieur ia", "12 semaines"],
    "data_analyst": ["data", "analyst", "power bi", "sql", "analyse"],
    "genai_weekend": ["genai", "weekend", "starter", "prompt", "no-code", "nocode"],
    "intro_workshop": ["atelier", "workshop", "decouverte", "2h", "2 heures"],
    "pack_artisan": ["artisan", "3000", "3 000"],
    "pack_commerce": ["commerce", "8000", "8 000", "boutique", "7anout"],
}


def fold(text: str) -> str:
    """Lowercase and strip accents so 'réduction' matches 'reduction'."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _compile(words: list[str]) -> re.Pattern:
    parts = []
    for w in words:
        w = fold(w)
        if not re.fullmatch(r"[\w' -]+", w):
            parts.append(re.escape(w))
        elif len(w) >= 5:  # prefix match: "formation" also catches "formations", "nthi9" catches "nthi9ch"
            parts.append(rf"(?<!\w){re.escape(w)}")
        else:
            parts.append(rf"(?<!\w){re.escape(w)}(?!\w)")
    return re.compile("|".join(parts))


_LEX_RX = {k: _compile(v) for k, v in LEX.items()}
_PRODUCT_RX = {k: _compile(v) for k, v in PRODUCT_HINTS.items()}


@dataclass
class Signals:
    tags: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=dict)

    def has(self, *names: str) -> bool:
        return any(n in self.tags for n in names)


def detect(text: str) -> Signals:
    t = fold(text)
    counts = {k: len(rx.findall(t)) for k, rx in _LEX_RX.items()}
    return Signals(tags={k for k, n in counts.items() if n}, counts=counts)


def product_mentioned(text: str, catalog_ids: list[str]) -> str | None:
    t = fold(text)
    for pid in catalog_ids:
        rx = _PRODUCT_RX.get(pid)
        if rx and rx.search(t):
            return pid
    return None


CONFIRM_RX = re.compile(
    r"^\s*(?:(?:ey|eyh|eyy|oui|ouii|yes|ok|okay|behi|d'accord|dac|mriguel|tamam|wakha|parfait)[\s,!.]*)*"
    r"(?:n ?confirmi|nconfirm|je confirme|j'confirme|i confirm|confirm[ée]?|confirmed|نأكد|ناكد|نكونفيرمي)"
    r"(?:[\s,!.]+[^\s]+){0,3}[\s!.]*$",
    re.IGNORECASE,
)


def is_explicit_confirmation(text: str) -> bool:
    """Deterministic: only an explicit confirmation phrase counts. Never an LLM opinion."""
    return bool(CONFIRM_RX.match(fold(text).strip()))
