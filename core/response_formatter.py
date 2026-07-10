import random
import re

from loguru import logger

from core.fallback_catalog import category_responses

MAX_LENGTH = 1000
DASH_PATTERN = re.compile(r"[-\u00ad‐‑‒–—―−]+")

# Raspunsuri de rezerva (produs negasit, eroare LLM, raspuns invalid).
# Se alege aleator, ca un cumparator care primeste mai multe fallback-uri
# sa nu vada de fiecare data exact acelasi mesaj.
FALLBACK_RESPONSES = [
    "Bună ziua! Vă mulțumesc pentru mesaj, revin cu detalii cât mai curând.",
    "Bună ziua! Am primit mesajul dumneavoastră și revin cu un răspuns în cel mai scurt timp.",
    "Mulțumesc pentru interes! Verific și vă răspund imediat ce pot.",
    "Bună! Mesajul dumneavoastră a ajuns la mine — revin în scurt timp cu toate detaliile.",
    "Bună ziua! Vă răspund în cel mai scurt timp posibil. Mulțumesc pentru răbdare!",
    "Mulțumesc pentru mesaj! Revin cât de repede pot cu răspunsul.",
    "Bună! Am văzut mesajul dumneavoastră și vă răspund cât de curând. O zi frumoasă!",
]

# pastrat pentru compatibilitate cu importurile existente
FALLBACK_RESPONSE = FALLBACK_RESPONSES[0]

# fraze care tradeaza un raspuns de AI — daca apar, folosim fallback-ul
FORBIDDEN_PHRASES = [
    "ca model de limbaj",
    "ca ai",
    "ca asistent ai",
    "as an ai",
    "as a language model",
    "sunt un model de limbaj",
    "sunt o inteligenta artificiala",
    "sunt o inteligență artificială",
]


def fallback_response(avoid: str | None = None, category: str | None = None) -> str:
    """Un raspuns de rezerva aleator.

    Cu `category` (detectata din mesajul cumparatorului), mesajul macar
    recunoaste subiectul intrebarii — vezi core/fallback_catalog.py.
    Cu `avoid` (ultimul raspuns trimis in conversatie), nu repeta acelasi
    mesaj de doua ori la rand pentru acelasi cumparator.
    """
    responses = category_responses(category) or FALLBACK_RESPONSES
    pool = [r for r in responses if sanitize_response(r) != avoid] or responses
    return sanitize_response(random.choice(pool))


def sanitize_response(response: str) -> str:
    """Elimina toate tipurile uzuale de liniuta din mesajul trimis."""
    response = DASH_PATTERN.sub(" ", str(response or ""))
    response = re.sub(r"\s+", " ", response).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", response)


def format_response(
    raw_response: str,
    avoid: str | None = None,
    category: str | None = None,
) -> str:
    """Valideaza raspunsul LLM. Returneaza raspunsul curatat sau un fallback."""
    response = sanitize_response(raw_response)

    if not response:
        logger.warning("Raspuns gol de la LLM — folosesc fallback.")
        return fallback_response(avoid, category)

    if len(response) > MAX_LENGTH:
        logger.warning(
            "Raspuns prea lung ({} caractere) — folosesc fallback.", len(response)
        )
        return fallback_response(avoid, category)

    lowered = response.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            logger.warning(
                "Raspunsul contine fraza interzisa '{}' — folosesc fallback.", phrase
            )
            return fallback_response(avoid, category)

    return response
