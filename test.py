"""Test end-to-end fara browser si fara cont OLX.

Ruleaza 3 mesaje simulate prin fluxul complet (matcher -> prompt -> LLM ->
formatter -> log). Daca GROQ_API_KEY e setat in .env foloseste Groq real,
altfel un LLM mock — deci merge complet offline.
"""
import os
import sys

from dotenv import load_dotenv
from loguru import logger

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.json_adapter import JSONAdapter
from core.message_handler import MessageHandler

# override=True: cheia din .env-ul proiectului are prioritate fata de
# variabilele globale Windows
load_dotenv(override=True)

# consola Windows e cp1252 by default — fortam UTF-8 pentru diacritice
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logger.remove()
logger.add(sys.stderr, level="DEBUG")


class MockLLMAdapter(BaseLLMAdapter):
    """LLM fals pentru rulare offline — raspunde generic dar valid."""

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return (
            "Bună ziua! Da, produsul este disponibil. "
            "Vă pot oferi toate detaliile de care aveți nevoie."
        )


def build_llm() -> BaseLLMAdapter:
    if os.environ.get("GROQ_API_KEY"):
        from adapters.llm.groq_adapter import GroqAdapter
        logger.info("GROQ_API_KEY gasit — folosesc Groq real.")
        return GroqAdapter()
    logger.warning("GROQ_API_KEY lipsa — folosesc MockLLMAdapter (offline).")
    return MockLLMAdapter()


mesaje_test = [
    {"id": "test_1", "text": "Bună ziua, mai aveți telefonul în stoc?", "olx_conversation_id": "fake_1"},
    {"id": "test_2", "text": "Cât costă livrarea pentru laptopul Lenovo?", "olx_conversation_id": "fake_2"},
    {"id": "test_3", "text": "Se poate negocia prețul la bicicleta Cube?", "olx_conversation_id": "fake_3"},
]


def main() -> None:
    handler = MessageHandler(llm=build_llm(), storage=JSONAdapter())

    for mesaj in mesaje_test:
        print("\n" + "=" * 70)
        print(f"CUMPĂRĂTOR ({mesaj['olx_conversation_id']}): {mesaj['text']}")
        raspuns = handler.process(mesaj)
        if raspuns is None:
            print("BOT: (conversatie deja procesata — niciun raspuns)")
        else:
            print(f"BOT: {raspuns}")
    print("\n" + "=" * 70)
    print("Test complet. Conversatiile au fost logate in data/conversations.json")


if __name__ == "__main__":
    main()
