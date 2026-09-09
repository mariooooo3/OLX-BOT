"""Evaluare explicabila a anunturilor suspecte.

Modulul nu interactioneaza cu OLX si nu trimite sesizari. Primeste numai
datele pe care utilizatorul le-a introdus sau importat in dashboard si
intoarce semnale verificabile, pentru o decizie manuala informata.
"""
from __future__ import annotations

import re
import unicodedata


REASON_SIGNALS = {
    "pret_redus": ("Preț neobișnuit de redus", 30),
    "plata_avans": ("Solicitare de plată în avans sau transfer direct", 30),
    "contact_extern": ("Contact sau mutarea conversației în afara platformei", 20),
    "descriere_suspecta": ("Expresii configurate pentru verificare", 20),
}


def _normal(text: object) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


def _terms(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split("\n") if item.strip()]


def default_rules() -> dict:
    return {
        "watched_titles": "",
        "suspicious_terms": "avans\ntransfer bancar\ntelegram\nwhatsapp",
        "max_price": None,
        "selected_reasons": ["pret_redus", "plata_avans", "contact_extern", "descriere_suspecta"],
        "reason": "Anunț suspect",
        "message_template": (
            "Anunțul „{title}” pare suspect: {signals}. "
            "Vă rog să verificați dacă respectă regulile platformei."
        ),
    }


def evaluate_listing(listing: dict, rules: dict | None = None) -> dict:
    """Calculeaza un scor 0..100 si explicatii pentru un singur anunt."""
    rules = {**default_rules(), **(rules or {})}
    title = str(listing.get("title") or "").strip()
    description = str(listing.get("description") or "").strip()
    haystack = _normal(f"{title}\n{description}")
    signals: list[dict] = []
    enabled = set(rules.get("selected_reasons") or REASON_SIGNALS)

    for watched in _terms(rules.get("watched_titles")):
        if _normal(watched) in _normal(title):
            signals.append({"kind": "title", "weight": 35,
                            "text": f"Titlu urmărit: „{watched}”"})
            break

    try:
        price = float(listing.get("price"))
        maximum = rules.get("max_price")
        if "pret_redus" in enabled and maximum not in (None, "") and price <= float(maximum):
            signals.append({"kind": "price", "weight": 30,
                            "text": f"Preț sub pragul configurat ({price:g} ≤ {float(maximum):g})"})
    except (TypeError, ValueError):
        pass

    matches = [term for term in _terms(rules.get("suspicious_terms")) if _normal(term) in haystack]
    if matches:
        shown = ", ".join(f"„{term}”" for term in matches[:3])
        advance = {"avans", "transfer bancar", "transfer direct", "iban"}
        external = {"telegram", "whatsapp", "email", "numar de telefon"}
        normalized_matches = {_normal(item) for item in matches}
        if "plata_avans" in enabled and normalized_matches & advance:
            signals.append({"kind": "terms", "weight": 30,
                            "text": "Solicitare de plată în avans sau transfer direct"})
        if "contact_extern" in enabled and normalized_matches & external:
            signals.append({"kind": "terms", "weight": 20,
                            "text": "Contact sau mutarea conversației în afara platformei"})
        if "descriere_suspecta" in enabled:
            signals.append({"kind": "terms", "weight": min(20, 10 + 5 * len(matches)),
                            "text": f"Expresii de verificat: {shown}"})

    score = min(100, sum(item["weight"] for item in signals))
    explanation = "; ".join(item["text"] for item in signals) or "Nu s-au detectat semnale configurate."
    template = str(rules.get("message_template") or default_rules()["message_template"])
    message = template.replace("{title}", title or "anunț fără titlu").replace("{signals}", explanation)
    return {
        **listing,
        "score": score,
        "signals": signals,
        "explanation": explanation,
        "reason": str(rules.get("reason") or "Anunț suspect"),
        "suggested_message": message,
    }
