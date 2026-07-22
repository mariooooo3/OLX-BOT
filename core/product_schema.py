"""Forma unui produs din catalog si migrarea catalogului vechi.

Modelul vechi avea 13 campuri, majoritatea greu de completat si slab folosite
in raspunsuri (categorie, subcategorie, atribute cheie-valoare, cuvinte cheie).
Rezultatul practic: ramaneau goale, iar botul nu avea din ce compune raspunsuri.

Modelul nou pastreaza structurat doar ce e FAPTIC si des intrebat — pentru
astea raspundem determinist, fara LLM, deci nu pot fi gresite — si comaseaza
restul intr-un singur text liber, scris ca un anunt.

  structurat:  pret, stoc, stare, negociabil, garantie, TVA
  text liber:  "despre" (fost: descriere + categorie + atribute + keywords)
  optional:    intrebari frecvente, trimise mereu in prompt
"""

# Cota implicita de TVA. Editabila per produs: nu o codam fix, ca sa nu
# ramana gresita daca legislatia se schimba.
DEFAULT_VAT_RATE = 21


def empty_product() -> dict:
    return {
        "id": "",
        "title": "",
        "price": 0,
        "currency": "RON",
        "stock": 0,
        "condition": "folosit",
        # cea mai frecventa intrebare de pe OLX; ca bifa, raspunsul e
        # determinist si nu mai depinde de potrivirea semantica
        "negotiable": False,
        "warranty": "",
        "vat": {
            "included": True,
            "deductible": False,
            "rate": DEFAULT_VAT_RATE,
        },
        "about": "",
        "faq": [],
    }


# Campurile vechi comasate in textul liber "about".
_MERGED_INTO_ABOUT = ("description", "category", "subcategory", "attributes")
# Campuri interne sau abandonate: nu ajung niciodata in promptul catre LLM.
INTERNAL_FIELDS = ("id", "keywords", "account_id", "account_label")


def _about_from_legacy(product: dict) -> str:
    """Compune textul liber din campurile vechi, fara sa piarda informatie."""
    parts: list[str] = []
    descriere = str(product.get("description") or "").strip()
    if descriere:
        parts.append(descriere)

    categorii = " / ".join(
        str(product.get(k) or "").strip()
        for k in ("category", "subcategory")
        if str(product.get(k) or "").strip()
    )
    if categorii:
        parts.append(f"Categorie: {categorii}")

    atribute = product.get("attributes") or {}
    if isinstance(atribute, dict):
        for cheie, valoare in atribute.items():
            cheie, valoare = str(cheie).strip(), str(valoare).strip()
            if cheie and valoare:
                parts.append(f"{cheie.capitalize()}: {valoare}")

    return "\n".join(parts)


def migrate_product(product: dict) -> dict:
    """Aduce un produs la forma noua. Idempotent: un produs deja migrat
    trece neschimbat, deci se poate rula la fiecare citire."""
    migrated = dict(product)

    if "about" not in migrated:
        migrated["about"] = _about_from_legacy(migrated)
    for camp in _MERGED_INTO_ABOUT:
        migrated.pop(camp, None)
    # "keywords" nu mai filtreaza nimic: potrivirea se face dupa titlul
    # anuntului OLX, care e sursa exacta de adevar
    migrated.pop("keywords", None)

    implicite = empty_product()
    for camp in ("negotiable", "warranty", "condition", "currency"):
        migrated.setdefault(camp, implicite[camp])

    vat = migrated.get("vat")
    if not isinstance(vat, dict):
        vat = {}
    migrated["vat"] = {**implicite["vat"], **vat}

    # livrarea a urcat la nivel de cont (aceeasi pentru toate anunturile)
    migrated.pop("shipping", None)
    return migrated


def public_product(product: dict) -> dict:
    """Produsul asa cum il vede LLM-ul: fara campuri interne, cu TVA-ul
    explicat in cuvinte (un model nu trebuie sa deduca sensul unui bool)."""
    public = {
        k: v for k, v in migrate_product(product).items()
        if k not in INTERNAL_FIELDS and k != "vat" and v not in ("", None, [])
    }
    public["tva"] = describe_vat(product)
    public.pop("faq", None)  # FAQ-urile se trimit separat, ca lista
    return public


def price_with_vat(product: dict) -> float | None:
    """Pretul cu TVA inclus, cand pretul afisat e fara TVA."""
    vat = migrate_product(product).get("vat", {})
    try:
        pret = float(product.get("price") or 0)
        cota = float(vat.get("rate") or DEFAULT_VAT_RATE)
    except (TypeError, ValueError):
        return None
    if not pret or vat.get("included", True):
        return None
    return round(pret * (1 + cota / 100), 2)


def describe_vat(product: dict) -> str:
    """Regimul de TVA in cuvinte, gata de pus in prompt sau intr-un raspuns."""
    vat = migrate_product(product).get("vat", {})
    inclus = bool(vat.get("included", True))
    text = "prețul afișat include TVA" if inclus else "prețul afișat este fără TVA"
    cu_tva = price_with_vat(product)
    if cu_tva is not None:
        moneda = product.get("currency") or "RON"
        text += f" (cu TVA: {cu_tva:g} {moneda})"
    if vat.get("deductible"):
        # fara cratima: raspunsurile trec printr-un curatator care inlocuieste
        # liniutele cu spatii, iar "TVA-ul" ar ajunge "TVA ul"
        text += ", TVA se poate deduce (se emite factură)"
    else:
        text += ", fără factură cu TVA deductibil"
    return text
