import json

from core.product_schema import public_product
from core.seller_info import describe as describe_seller

SYSTEM_PROMPT = """Ești un asistent de vânzări pentru un vânzător de pe OLX.
Răspunzi politicos, concis și în română.
Folosești doar informațiile furnizate — nu inventa detalii.
Dacă informația cerută nu apare mai jos, spune că verifici și revii.
Când o întrebare frecventă acoperă întrebarea cumpărătorului, răspunde pe baza
ei, cu aceleași informații.
Nu promite lucruri care nu sunt menționate explicit."""

USER_PROMPT_TEMPLATE = """Produs în discuție:
{product_json}
{seller_block}{faq_block}
Mesajul cumpărătorului:
{buyer_message}

Răspunde la mesajul cumpărătorului."""

SELLER_TEMPLATE = """
Informații despre vânzător (valabile pentru toate anunțurile):
{seller}
"""

# TOATE intrebarile frecvente ajung in prompt, nu doar cea potrivita semantic.
# Inainte, daca scorul de potrivire era sub prag, LLM-ul nu vedea deloc FAQ-ul
# si raspundea generic desi vanzatorul scrisese raspunsul — "se pierdea in
# embedding". Un model alege bine dintr-o lista scurta; un prag numeric nu.
FAQ_TEMPLATE = """
Întrebări frecvente și răspunsurile date de vânzător:
{entries}
"""

FAQ_HIGHLIGHT = """
Cea mai apropiată de mesajul cumpărătorului pare: {question!r}
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def _faq_block(faq: list | None, highlight: str | None) -> str:
    entries = [
        (str(f.get("question") or "").strip(), str(f.get("answer") or "").strip())
        for f in (faq or [])
    ]
    entries = [(q, a) for q, a in entries if q and a]
    if not entries:
        return ""
    listed = "\n".join(f"- Î: {q}\n  R: {a}" for q, a in entries)
    block = FAQ_TEMPLATE.format(entries=listed)
    if highlight:
        block += FAQ_HIGHLIGHT.format(question=highlight)
    return block


def build_user_prompt(
    product: dict,
    buyer_message: str,
    faq_hint: tuple[str, str] | None = None,
    seller: dict | None = None,
) -> str:
    """Promptul complet: produsul (fara campuri interne), informatiile
    vanzatorului si toate intrebarile frecvente.

    `faq_hint` doar EVIDENTIAZA intrebarea cea mai apropiata; lista completa
    e trimisa oricum, deci o potrivire semantica ratata nu mai ascunde
    raspunsul scris de vanzator.
    """
    product_json = json.dumps(public_product(product), ensure_ascii=False, indent=2)
    seller_text = describe_seller(seller) if seller else ""
    seller_block = SELLER_TEMPLATE.format(seller=seller_text) if seller_text else ""
    return USER_PROMPT_TEMPLATE.format(
        product_json=product_json,
        seller_block=seller_block,
        faq_block=_faq_block(product.get("faq"), faq_hint[0] if faq_hint else None),
        buyer_message=buyer_message,
    )
