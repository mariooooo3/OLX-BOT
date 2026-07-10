import tempfile
import unittest
from pathlib import Path

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.json_adapter import JSONAdapter
from core.message_handler import MessageHandler
from core.response_formatter import FALLBACK_RESPONSES, format_response, sanitize_response


class FailingLLM(BaseLLMAdapter):
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("Disponibilitatea trebuie stabilita din stoc, fara LLM")


class MessageRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = JSONAdapter(Path(tempfile.mkdtemp()))
        self.storage.save_product({
            "id": "prod_1",
            "title": "iPhone 15 Pro",
            "stock": 4,
            "keywords": ["iphone"],
        })
        self.handler = MessageHandler(FailingLLM(), self.storage)

    def test_availability_variants_use_catalog_stock(self) -> None:
        variants = [
            "Produsul este disponibil?",
            "Produsul mai este pe stoc?",
            "Mai este?",
            "Se poate?",
        ]

        for index, text in enumerate(variants):
            with self.subTest(text=text):
                response = self.handler.process({
                    "id": f"message_{index}",
                    "text": text,
                    "olx_conversation_id": f"conversation_{index}",
                    "ad_title": "iPhone 15 Pro",
                })
                self.assertIn(response, {
                    "Da, produsul este disponibil.",
                    "Da, mai este în stoc.",
                })

    def test_stock_quantity_question_returns_exact_catalog_count(self) -> None:
        variants = [
            "Câte produse mai sunt pe stoc?",
            "Câte bucăți aveți în stoc?",
            "Ce stoc mai aveți?",
        ]

        for index, text in enumerate(variants):
            with self.subTest(text=text):
                response = self.handler.process({
                    "id": f"stock_message_{index}",
                    "text": text,
                    "olx_conversation_id": f"stock_conversation_{index}",
                    "ad_title": "iPhone 15 Pro",
                })
                self.assertEqual(response, "Mai sunt 4 produse în stoc.")

    def test_response_never_contains_dash_characters(self) -> None:
        responses = [
            format_response("Da -- produsul este disponibil — îl puteți comanda acum."),
            *(sanitize_response(response) for response in FALLBACK_RESPONSES),
        ]

        for response in responses:
            for dash in "-‐‑‒–—―−":
                self.assertNotIn(dash, response)


if __name__ == "__main__":
    unittest.main()
