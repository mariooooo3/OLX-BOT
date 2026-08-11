"""Informatiile vanzatorului, comune tuturor anunturilor unui cont.

Locatia, livrarea si metodele de plata sunt aceleasi pentru tot ce vinde un
cont, deci se completeaza o singura data, nu la fiecare produs.

Avantaj important: la aceste intrebari botul poate raspunde CHIAR SI cand
niciun produs din catalog nu se potriveste cu anuntul — "din ce oras esti?"
sau "trimiti prin curier?" nu depind de produs.
"""
import re
import unicodedata


DEFAULT_SELLER_INFO = {
    # de unde se poate ridica personal
    "city": "",
    "pickup_available": True,
    # livrare prin curier
    "delivery_available": False,
    "courier": "",
    # "buyer" | "seller" — cine plateste transportul
    "delivery_paid_by": "buyer",
    # ex. "numerar la ridicare, transfer bancar"
    "payment_methods": "",
}

SELLER_INFO_FIELDS = tuple(DEFAULT_SELLER_INFO)


def normalize(info: dict | None) -> dict:
    """Completeaza campurile lipsa cu valorile implicite."""
    merged = dict(DEFAULT_SELLER_INFO)
    for key, value in (info or {}).items():
        if key in DEFAULT_SELLER_INFO:
            merged[key] = value
    return merged


def is_configured(info: dict) -> bool:
    """A completat cineva informatiile, sau sunt doar valorile implicite?

    Distinctia conteaza: `delivery_available` e False implicit, dar asta NU
    inseamna ca vanzatorul a spus ca nu trimite prin curier. Fara verificarea
    asta, un cont nou ar refuza ferm livrarea unor cumparatori reali.

    Toate campurile stau in acelasi card din interfata, deci daca s-a
    completat oricare dintre ele, comutatoarele au fost vazute si lasate
    dinadins asa cum sunt.
    """
    info = normalize(info)
    return bool(
        info["city"]
        or info["courier"]
        or info["payment_methods"]
        or info["delivery_available"]
    )


# --------------------------------------------------------------------- #
# recunoasterea intrebarii
# --------------------------------------------------------------------- #

# Potrivim pe RADACINA, nu pe cuvantul exact: altfel "locatia", "transportul"
# si "plateste" nu se potriveau cu "locatie", "transport" si "plata", iar
# intrebari uzuale cadeau pe raspunsul generic.
LOCATION_STEMS = ("unde", "oras", "locat", "localit", "adres", "zona", "judet")
PICKUP_STEMS = ("ridic", "personal", "preiau", "preluare", "venim", "vin")
DELIVERY_STEMS = (
    "livr", "curier", "transport", "trimit", "expedi", "colet",
    "posta", "cargus", "sameday", "fan",
)
PAYMENT_STEMS = (
    "plat", "achit", "numerar", "cash", "transfer", "ramburs", "card",
    "banca", "bancar", "op",
)
PAYER_STEMS = ("cine", "suporta", "platit")
# "de unde ai luat-o?" intreaba de PROVENIENTA produsului, nu de unde se
# ridica. Fara excluderea asta, botul raspundea cu orasul lui.
PROVENANCE_STEMS = (
    "luat", "cumparat", "achizit", "gasit", "procurat", "comandat", "adus",
)


def _tokens(text: str) -> list[str]:
    """Cuvintele mesajului, fara diacritice si semne de punctuatie."""
    text = unicodedata.normalize("NFD", str(text or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).split()


def _has(tokens: list[str], stems: tuple[str, ...]) -> bool:
    return any(token.startswith(stem) for token in tokens for stem in stems)


# --------------------------------------------------------------------- #
# formularea raspunsurilor
# --------------------------------------------------------------------- #

def _location_description(info: dict) -> str:
    if info["city"]:
        if info["pickup_available"]:
            return f"Produsul se poate ridica personal din {info['city']}."
        return f"Vânzătorul este din {info['city']}."
    if info["pickup_available"]:
        return "Produsul se poate ridica personal."
    return ""


def _pickup_description(info: dict) -> str:
    """Raspuns la "pot ridica personal?" — intrebare de DA/NU.

    Separat de locatie: cu ridicarea dezactivata, "Vanzatorul este din Iasi"
    nu raspundea la intrebare si lasa impresia ca se poate ridica.
    """
    if not info["pickup_available"]:
        return "Nu, produsul nu se poate ridica personal."
    if info["city"]:
        return f"Da, produsul se poate ridica personal din {info['city']}."
    return "Da, produsul se poate ridica personal."


def _delivery_description(info: dict) -> str:
    if not info["delivery_available"]:
        return "Nu se face livrare prin curier."
    curier = f" prin {info['courier']}" if info["courier"] else ""
    platitor = (
        "transportul este plătit de cumpărător"
        if info["delivery_paid_by"] == "buyer"
        else "transportul este plătit de vânzător"
    )
    return f"Se trimite{curier} în țară, {platitor}."


def _payer_description(info: dict) -> str:
    if not info["delivery_available"]:
        return "Nu se face livrare prin curier."
    if info["delivery_paid_by"] == "buyer":
        return "Transportul este plătit de cumpărător."
    return "Transportul este plătit de vânzător."


def _payment_description(info: dict) -> str:
    if not info["payment_methods"]:
        return ""
    return f"Metode de plată acceptate: {info['payment_methods']}."


def answer(buyer_message: str, info: dict) -> str | None:
    """Raspuns scurt din informatiile vanzatorului, cand sunt suficiente.

    Intoarce None cand intrebarea nu e despre vanzator sau cand campul cerut
    nu e completat — mai bine un raspuns generic decat unul inventat.
    """
    info = normalize(info)
    tokens = _tokens(buyer_message)
    if not tokens or not is_configured(info):
        return None

    # "de unde ai luat-o?" nu e despre locatia de ridicare
    if _has(tokens, PROVENANCE_STEMS) and _has(tokens, ("unde",)):
        return None

    # cine plateste transportul — mai specific decat livrarea in general
    if _has(tokens, PAYER_STEMS) and _has(tokens, DELIVERY_STEMS):
        return _payer_description(info)

    # ridicare personala: intrebare de da/nu, inaintea locatiei
    if _has(tokens, PICKUP_STEMS):
        return _pickup_description(info)

    if _has(tokens, DELIVERY_STEMS):
        # "cu ce curier trimiteti?" fara curier completat: nu inventam
        asks_courier = _has(tokens, ("curier",)) and not _has(tokens, ("livr",))
        if info["delivery_available"] and asks_courier and not info["courier"]:
            return None
        return _delivery_description(info)

    if _has(tokens, LOCATION_STEMS):
        return _location_description(info) or None

    if _has(tokens, PAYMENT_STEMS):
        return _payment_description(info) or None

    return None


def describe(info: dict | None) -> str:
    """Informatiile vanzatorului in cuvinte, pentru prompt.

    Intoarce sir gol cand nu s-a completat nimic — asa nu bagam in prompt
    propozitii goale care ar invita modelul sa inventeze, si nici nu afirmam
    ca nu se face livrare doar pentru ca asa e valoarea implicita.
    """
    info = normalize(info)
    if not is_configured(info):
        return ""

    parts: list[str] = []

    location = _location_description(info)
    if location:
        parts.append(location)

    parts.append(_delivery_description(info))

    payment = _payment_description(info)
    if payment:
        parts.append(payment)

    return " ".join(parts)
