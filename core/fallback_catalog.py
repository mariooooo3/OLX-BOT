"""Fallback-uri categorisite: cand LLM-ul nu poate raspunde (eroare, raspuns
invalid, produs negasit), mesajul hardcodat macar recunoaste subiectul
intrebarii ("am vazut intrebarea despre livrare...") in loc de un generic
"revin cu detalii".

IMPORTANT: fallback-urile NU raspund la intrebare (nu stiu daca pretul e
negociabil sau daca se face livrare — ar inventa). Doar confirma subiectul
si promit revenirea, deci raman 100% adevarate indiferent de produs.

Detectarea categoriei: intai regex pe cuvinte distinctive (precis si fara
dependinte), apoi semantic pe fraze-ancora daca embeddings sunt disponibile.
"""
import re

from core.faq_matcher import lexical_score, normalize_text

# prag pentru detectarea semantica a categoriei (ancorele sunt fraze
# scurte si generice, deci pragul e mai relaxat decat la FAQ)
CATEGORY_THRESHOLD = 0.45

CATEGORIES: dict[str, dict] = {
    "pret": {
        "pattern": re.compile(
            r"\b(pret|pretul|negocia|negociabil|ieftin|scump|lei|euro|ron"
            r"|oferta|reducere|lasi|lasati|ultimul|costa|cost)\b"
        ),
        "anchors": [
            "care este ultimul pret",
            "pretul este negociabil",
            "lasi mai ieftin de atat",
            "cat costa produsul",
        ],
        "responses": [
            "Bună ziua! Am văzut întrebarea legată de preț, revin în cel mai scurt timp cu un răspuns exact.",
            "Mulțumesc pentru mesaj! Verific și revin imediat cu detaliile despre preț.",
            "Bună! Întrebarea despre preț a ajuns la mine, revin cu un răspuns cât de curând.",
        ],
    },
    "livrare": {
        "pattern": re.compile(
            r"\b(livrare|livrezi|livrati|curier|transport|trimiti|trimiteti"
            r"|expediezi|expediati|posta|easybox|colet|ramburs)\b"
        ),
        "anchors": [
            "faceti livrare prin curier",
            "trimiteti in alta localitate",
            "cat costa transportul",
            "se poate trimite prin easybox",
        ],
        "responses": [
            "Bună ziua! Am văzut întrebarea despre livrare, verific opțiunile și revin cu un răspuns exact.",
            "Mulțumesc pentru mesaj! Revin în scurt timp cu detaliile despre livrare.",
            "Bună! Verific variantele de livrare și vă răspund cât de curând.",
        ],
    },
    "stare": {
        "pattern": re.compile(
            r"\b(stare|starea|nou|noua|folosit|folosita|defect|defecte"
            r"|zgariat|zgarieturi|uzat|uzata|functioneaza|probleme|garantie)\b"
        ),
        "anchors": [
            "in ce stare este produsul",
            "este nou sau folosit",
            "are defecte sau zgarieturi",
            "functioneaza bine",
        ],
        "responses": [
            "Bună ziua! Am văzut întrebarea despre starea produsului, revin imediat cu toate detaliile.",
            "Mulțumesc pentru mesaj! Verific detaliile despre starea produsului și revin cât de curând.",
            "Bună! Revin în scurt timp cu un răspuns exact despre starea produsului.",
        ],
    },
    "locatie": {
        "pattern": re.compile(
            r"\b(unde|oras|orasul|zona|adresa|ridic|ridicare|ridicat"
            r"|vizionare|intalnim|intalnire|personal|vad|vedea)\b"
        ),
        "anchors": [
            "de unde se poate ridica produsul",
            "pot veni sa il vad personal",
            "in ce oras va aflati",
            "unde ne putem intalni",
        ],
        "responses": [
            "Bună ziua! Am văzut întrebarea despre locul de ridicare, revin imediat cu detaliile.",
            "Mulțumesc pentru mesaj! Revin în scurt timp cu detalii despre locație și vizionare.",
            "Bună! Vă răspund cât de curând cu detaliile despre ridicare și vizionare.",
        ],
    },
    "salut": {
        # doar cand TOT mesajul e un salut scurt, altfel prioritate au
        # categoriile de continut
        "pattern": re.compile(
            r"^(buna( ziua| seara| dimineata)?|salut(are)?|servus|hei|hello|hi"
            r"|noroc)[ !.?]*$"
        ),
        "anchors": [],  # regex-ul acopera complet cazul; semantic ar prinde prea mult
        "responses": [
            "Bună ziua! Cu ce vă pot ajuta legat de anunț?",
            "Bună! Cu ce vă pot ajuta legat de produs?",
            "Bună ziua! Vă ascult, ce doriți să știți despre produs?",
        ],
    },
}

# ordinea de verificare: continut inainte de salut (un "buna ziua, faceti
# livrare?" e despre livrare, nu salut)
_CATEGORY_ORDER = ["pret", "livrare", "stare", "locatie", "salut"]


def detect_category(message: str, matcher=None) -> str | None:
    """Categoria intrebarii, pentru alegerea fallback-ului potrivit.

    `matcher` (FAQMatcher, optional) da acces la embeddings cu cache pentru
    detectarea semantica atunci cand regex-ul nu prinde nimic. Returneaza
    None cand nu se potriveste nicio categorie (se foloseste pool-ul general).
    """
    normalized = normalize_text(message)
    if not normalized:
        return None

    for name in _CATEGORY_ORDER:
        if CATEGORIES[name]["pattern"].search(normalized):
            return name

    embeddings = getattr(matcher, "embeddings", None)
    if embeddings is None:
        return None
    anchored = [(n, a) for n in _CATEGORY_ORDER for a in CATEGORIES[n]["anchors"]]
    anchor_vecs = matcher._embed_cached([a for _, a in anchored])
    msg_vecs = embeddings.embed([message])
    if anchor_vecs is None or not msg_vecs:
        return None
    msg_vec = msg_vecs[0]
    best_name, best_score = None, 0.0
    for (name, anchor), vec in zip(anchored, anchor_vecs):
        score = sum(x * y for x, y in zip(msg_vec, vec))
        # ancorele sunt scurte — combinatia cu lexical intareste potrivirea
        score = max(score, (score + lexical_score(message, anchor)) / 2)
        if score > best_score:
            best_name, best_score = name, score
    return best_name if best_score >= CATEGORY_THRESHOLD else None


def category_responses(category: str | None) -> list[str] | None:
    """Pool-ul de mesaje al categoriei (None -> se foloseste cel general)."""
    if category and category in CATEGORIES:
        return CATEGORIES[category]["responses"]
    return None
