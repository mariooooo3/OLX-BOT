import json

SYSTEM_PROMPT = """Ești un asistent de vânzări pentru un vânzător de pe OLX.
Răspunzi politicos, concis și în română.
Folosești doar informațiile furnizate despre produs — nu inventa detalii.
Dacă nu știi răspunsul la o întrebare, spune că vei verifica și revii.
Nu promite lucruri care nu sunt menționate explicit în datele produsului."""

USER_PROMPT_TEMPLATE = """Produs în discuție:
{product_json}

Mesajul cumpărătorului:
{buyer_message}

Răspunde la mesajul cumpărătorului."""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_prompt(product: dict, buyer_message: str) -> str:
    product_json = json.dumps(product, ensure_ascii=False, indent=2)
    return USER_PROMPT_TEMPLATE.format(
        product_json=product_json, buyer_message=buyer_message
    )
