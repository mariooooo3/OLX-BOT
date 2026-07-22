"""Potrivire semantica intre mesajul cumparatorului si FAQ-ul produsului.

Scorul e hibrid, calibrat pe intrebari reale de OLX in romana:
  semantic = max(cos(mesaj, intrebare), cos(mesaj, intrebare+raspuns))
  lexical  = suprapunere de cuvinte-continut cu potrivire pe radacina
             ("negocia" ~ "negociabil"), fara diacritice
  scor     = max(semantic, (semantic + lexical) / 2)
Fara embeddings (model indisponibil / EMBEDDINGS_BACKEND=off), scorul
ramane doar cel lexical — mai slab, dar functional.

Praguri (masurate cu paraphrase-multilingual-MiniLM-L12-v2: potrivirile
corecte urca peste ~0.77, cele gresite raman sub ~0.56):
  >= direct_threshold (0.75): raspunsul vanzatorului se trimite direct,
     fara LLM — exact ce a scris omul, zero halucinatie;
  >= hint_threshold (0.55): FAQ-ul cel mai relevant e evidentiat in
     promptul LLM.

Vectorii intrebarilor FAQ se cache-uiesc pe disc (cheie = hash continut),
deci modelul embeduieste doar mesajul nou la fiecare poll.
"""
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

DIRECT_THRESHOLD = float(os.environ.get("FAQ_DIRECT_THRESHOLD", "0.75"))
HINT_THRESHOLD = float(os.environ.get("FAQ_HINT_THRESHOLD", "0.55"))
CACHE_PATH = Path("data/embeddings_cache.json")

# cuvinte fara continut — nu conteaza la suprapunerea lexicala
STOPWORDS = {
    "e", "este", "sunt", "a", "al", "ai", "ale", "un", "o", "de", "la", "in",
    "pe", "cu", "si", "sa", "se", "ce", "care", "mai", "nu", "da", "ma", "il",
    "prin", "din", "sau", "ati", "pot", "poate", "am", "are", "fi", "cat",
    "cata", "cate", "va", "vă", "imi", "iti", "mi", "ti", "as", "ar", "fie",
    "produs", "produsul", "produse", "anunt", "anuntul",
    # Politete si formule de deschidere/incheiere: nu spun nimic despre
    # produs, dar diluau scorul mesajelor scrise frumos ("Buna ziua, as vrea
    # sa stiu daca pretul este negociabil, multumesc").
    # NU includem "unde", "cand", "cum" — acelea chiar disting intrebarea.
    "buna", "bună", "ziua", "seara", "dimineata", "salut", "salutare",
    "multumesc", "multumim", "merci", "rog", "scuze", "scuzati", "va_rog",
    "vrea", "vreau", "doresc", "dori", "stiu", "afla", "spune", "spuneti",
    "interesat", "interesata", "interesa", "putea", "posibil",
    # conjunctii si particule fara sens propriu in intrebari
    "daca", "dar", "iar", "deci", "oare", "totusi", "cumva",
}


def normalize_text(text: str) -> str:
    """lowercase + fara diacritice + doar litere/cifre, pentru comparatii."""
    text = unicodedata.normalize("NFD", str(text or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def _content_tokens(text: str) -> set[str]:
    return {t for t in normalize_text(text).split()
            if t not in STOPWORDS and len(t) > 1}


def _covered(source: set[str], target: set[str]) -> int:
    """Cate cuvinte din `source` se regasesc in `target`, cu potrivire pe
    radacina (primele 5 litere sau prefix comun), ca 'negocia' sa se
    potriveasca cu 'negociabil' si 'livrare' cu 'livrezi'."""
    return sum(
        1 for x in source
        if any(x[:5] == y[:5] or x.startswith(y) or y.startswith(x) for y in target)
    )


def lexical_score(a: str, b: str) -> float:
    """Suprapunerea cuvintelor-continut, masurata SIMETRIC (F1).

    Impartirea la minimul lungimilor dadea 1.0 oricarui mesaj scurt care e
    submultime a intrebarii din FAQ: "care este pretul?" se reduce la
    {pretul}, complet continut in "pretul este negociabil", si primea scor
    maxim — desi e alta intrebare. Cu media armonica intre cat acopera
    mesajul din intrebare si invers, cele doua se separa (1.00 vs 0.67).
    """
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 0.0
    hits_a, hits_b = _covered(ta, tb), _covered(tb, ta)
    if not hits_a or not hits_b:
        return 0.0
    precision = hits_a / len(ta)
    recall = hits_b / len(tb)
    return 2 * precision * recall / (precision + recall)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class FAQMatch:
    question: str
    answer: str
    score: float
    direct: bool  # True: raspunsul se trimite direct, fara LLM


class FAQMatcher:
    def __init__(
        self,
        embeddings=None,
        direct_threshold: float = DIRECT_THRESHOLD,
        hint_threshold: float = HINT_THRESHOLD,
        cache_path: str | Path = CACHE_PATH,
    ):
        self.embeddings = embeddings
        self.direct_threshold = direct_threshold
        self.hint_threshold = hint_threshold
        self.cache_path = Path(cache_path)
        self._cache: dict[str, list[float]] | None = None

    # ---- cache pe disc pentru vectorii FAQ (stabili intre poll-uri) ----

    def _cache_key(self, text: str) -> str:
        model = getattr(self.embeddings, "model_name", "?")
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        return f"{model}:{digest}"

    def _load_cache(self) -> dict:
        if self._cache is None:
            self._cache = {}
            if self.cache_path.exists():
                try:
                    self._cache = json.loads(
                        self.cache_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    self._cache = {}
        return self._cache

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("Nu am putut salva cache-ul de embeddings: {}", e)

    def _embed_cached(self, texts: list[str]) -> list[list[float]] | None:
        """Embeddings cu cache pe disc; None daca modelul nu e disponibil."""
        if self.embeddings is None:
            return None
        cache = self._load_cache()
        missing = [t for t in texts if self._cache_key(t) not in cache]
        if missing:
            vectors = self.embeddings.embed(missing)
            if vectors is None:
                return None
            for text, vec in zip(missing, vectors):
                cache[self._cache_key(text)] = vec
            self._save_cache()
        return [cache[self._cache_key(t)] for t in texts]

    # ---- potrivirea propriu-zisa ----

    def best_match(self, message: str, faq: list[dict]) -> FAQMatch | None:
        """Cea mai potrivita intrare FAQ pentru mesaj, cu scorul hibrid.

        Returneaza None cand FAQ-ul e gol sau scorul maxim e sub pragul
        de hint (nu merita nici macar evidentiat in prompt).
        """
        entries = [
            (str(f.get("question", "")).strip(), str(f.get("answer", "")).strip())
            for f in faq or []
        ]
        entries = [(q, a) for q, a in entries if q and a]
        if not entries or not str(message or "").strip():
            return None

        lex = [lexical_score(message, q) for q, _ in entries]

        sem = [0.0] * len(entries)
        # vectorii FAQ vin (aproape) mereu din cache; doar mesajul e nou
        faq_texts = [q for q, _ in entries] + [f"{q} {a}" for q, a in entries]
        faq_vecs = self._embed_cached(faq_texts)
        msg_vecs = self.embeddings.embed([message]) if self.embeddings else None
        if faq_vecs is not None and msg_vecs:
            msg_vec = msg_vecs[0]
            n = len(entries)
            sem = [
                max(_dot(msg_vec, faq_vecs[i]), _dot(msg_vec, faq_vecs[n + i]))
                for i in range(n)
            ]
            scores = [max(s, (s + l) / 2) for s, l in zip(sem, lex)]
        else:
            # fara model semantic: doar lexical (potrivirile perfecte raman
            # peste pragul direct, restul cad pe LLM)
            scores = lex

        best = max(range(len(entries)), key=lambda i: scores[i])
        score = scores[best]
        question, answer = entries[best]
        logger.debug(
            "FAQ match: {!r} -> {!r} (scor {:.3f}, sem {:.2f}, lex {:.2f})",
            message, question, score, sem[best], lex[best],
        )
        if score < self.hint_threshold:
            return None
        return FAQMatch(
            question=question,
            answer=answer,
            score=score,
            direct=score >= self.direct_threshold,
        )
