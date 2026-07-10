"""Test offline pentru MVP2 — fara browser, fara OLX, fara Groq.

Dovedeste ca:
  1. DBAdapter (SQLite) face round-trip la produse si conversatii, identic
     cu contractul JSONAdapter.
  2. Coada de joburi functioneaza cap-coada: enqueue -> worker (claim ->
     genereaza raspuns cu un LLM mock -> complete) -> sender (claim_to_send
     -> mark_sent).

Ruleaza intr-o baza SQLite temporara, deci nu atinge datele reale.
"""
import sys
import tempfile
from pathlib import Path

from loguru import logger

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.db_adapter import DBAdapter
from core.message_handler import MessageHandler
from core.product_matcher import match_product

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
logger.remove()
logger.add(sys.stderr, level="INFO")


class MockLLM(BaseLLMAdapter):
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "Bună ziua! Da, produsul este disponibil în stoc."


SAMPLE_PRODUCT = {
    "id": "prod_001",
    "title": "Samsung Galaxy A54 5G 128GB Negru",
    "category": "electronice",
    "subcategory": "telefoane",
    "price": 1200,
    "currency": "RON",
    "stock": 3,
    "condition": "nou",
    "description": "Nou, sigilat, garanție 12 luni.",
    "attributes": {"brand": "Samsung"},
    "faq": [{"question": "Livrare?", "answer": "Da, Fan Courier."}],
    "shipping": {"available": True, "courier": "Fan Courier",
                 "cost_paid_by": "buyer", "estimated_days": 2},
    "keywords": ["samsung", "galaxy", "a54", "telefon"],
}


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    db_url = f"sqlite:///{tmp.as_posix()}/test.db"
    storage = DBAdapter(db_url)

    print("\n== 1. Produse (round-trip DB) ==")
    storage.save_product(SAMPLE_PRODUCT)
    products = storage.get_products()
    assert len(products) == 1, "produsul nu a fost salvat"
    assert products[0]["title"] == SAMPLE_PRODUCT["title"]
    assert products[0]["keywords"] == SAMPLE_PRODUCT["keywords"], "JSON column stricat"
    print("  OK — produs salvat si citit corect (inclusiv campuri JSON)")

    print("\n== 2. Coada de joburi (producer -> worker -> sender) ==")
    handler = MessageHandler(llm=MockLLM(), storage=storage)

    # producator: mesaj nou -> job
    job_id = storage.enqueue_job("olx_conv_1", "Bună, mai aveți telefonul Samsung?")
    assert storage.has_active_job("olx_conv_1"), "jobul activ nu e detectat"
    print(f"  enqueue -> {job_id}")

    # worker: claim -> genereaza -> complete
    job = storage.claim_next_job()
    assert job is not None and job["status"] == "processing"
    product = match_product(job["buyer_message"], storage.get_products())
    response = handler.process({
        "id": job["id"],
        "text": job["buyer_message"],
        "olx_conversation_id": job["olx_conversation_id"],
    })
    assert response, "workerul nu a generat raspuns"
    storage.complete_job(job["id"], response, product["id"] if product else None)
    print(f"  worker done -> raspuns: {response!r}")
    print(f"  produs potrivit: {product['id'] if product else None}")

    # coada goala acum
    assert storage.claim_next_job() is None, "coada ar trebui sa fie goala"

    # sender: claim_to_send -> mark_sent
    to_send = storage.claim_job_to_send()
    assert to_send is not None and to_send["response_text"] == response
    storage.mark_conversation_status(
        to_send["olx_conversation_id"], to_send["buyer_message"], "sent"
    )
    storage.mark_job_sent(to_send["id"])
    print(f"  sender -> job {to_send['id']} marcat 'sent'")

    print("\n== 3. Conversatie logata + dedup ==")
    convos = storage.get_conversations()
    assert len(convos) == 1, "conversatia nu a fost logata"
    assert storage.is_processed(
        "olx_conv_1", "Bună, mai aveți telefonul Samsung?"
    ), "dedup: acelasi mesaj ar trebui sarit"
    assert not storage.is_processed(
        "olx_conv_1", "Si cat costa livrarea?"
    ), "un mesaj NOU in aceeasi conversatie trebuie procesat"
    print(f"  {len(convos)} conversatie logata, dedup per mesaj OK")

    print("\n== Statistici finale ==")
    print(f"  {storage.stats()}")
    print("\nTOATE TESTELE MVP2 AU TRECUT ✔")


if __name__ == "__main__":
    main()
