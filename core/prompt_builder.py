import json

SYSTEM_PROMPT = """Ești un asistent de vânzări pentru un vânzător de pe OLX.
Răspunzi politicos, concis și în română.
Folosești doar informațiile furnizate despre produs — nu inventa detalii.
Dacă nu știi răspunsul la o întrebare, spune că vei verifica și revii.
Nu promite lucruri care nu sunt menționate explicit în datele produsului."""

USER_PROMPT_TEMPLATE = """Produs în discuție:
{product_json}
{faq_hint}
Mesajul cumpărătorului:
{buyer_message}

Răspunde la mesajul cumpărătorului."""

FAQ_HINT_TEMPLATE = """
Cea mai relevantă întrebare frecventă pentru acest mesaj (folosește răspunsul
ei dacă întrebarea cumpărătorului are același sens):
Î: {question}
R: {answer}
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_prompt(
    product: dict, buyer_message: str, faq_hint: tuple[str, str] | None = None
) -> str:
    """Promptul cu datele produsului; `faq_hint` = (intrebare, raspuns) din
    FAQ cu potrivire semantica medie — evidentiata explicit pentru LLM."""
    product_json = json.dumps(product, ensure_ascii=False, indent=2)
    hint = ""
    if faq_hint:
        hint = FAQ_HINT_TEMPLATE.format(question=faq_hint[0], answer=faq_hint[1])
    return USER_PROMPT_TEMPLATE.format(
        product_json=product_json, buyer_message=buyer_message, faq_hint=hint
    )
