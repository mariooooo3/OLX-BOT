"""Informatiile vanzatorului, comune tuturor anunturilor unui cont.

Locatia, livrarea si metodele de plata sunt aceleasi pentru tot ce vinde un
cont, deci se completeaza o singura data, nu la fiecare produs.

Avantaj important: la aceste intrebari botul poate raspunde CHIAR SI cand
niciun produs din catalog nu se potriveste cu anuntul — "din ce oras esti?"
sau "trimiti prin curier?" nu depind de produs.
"""

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


def describe(info: dict | None) -> str:
    """Informatiile vanzatorului in cuvinte, pentru prompt.

    Intoarce sir gol cand nu s-a completat nimic — asa nu bagam in prompt
    propozitii goale care ar invita modelul sa inventeze.
    """
    info = normalize(info)
    parts: list[str] = []

    if info["city"]:
        if info["pickup_available"]:
            parts.append(f"Produsul se poate ridica personal din {info['city']}.")
        else:
            parts.append(f"Vânzătorul este din {info['city']}.")
    elif info["pickup_available"]:
        parts.append("Produsul se poate ridica personal.")

    if info["delivery_available"]:
        curier = f" prin {info['courier']}" if info["courier"] else ""
        platitor = (
            "transportul este plătit de cumpărător"
            if info["delivery_paid_by"] == "buyer"
            else "transportul este plătit de vânzător"
        )
        parts.append(f"Se trimite{curier} în țară, {platitor}.")
    else:
        parts.append("Nu se face livrare prin curier.")

    if info["payment_methods"]:
        parts.append(f"Metode de plată acceptate: {info['payment_methods']}.")

    return " ".join(parts)
