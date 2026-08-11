import tempfile
import unittest
from pathlib import Path

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.json_adapter import JSONAdapter
from core.message_handler import MessageHandler
from core.response_formatter import FALLBACK_RESPONSES, format_response, sanitize_response
from core.seller_info import answer as answer_seller
from core.seller_info import describe as describe_seller
from core.seller_info import answer as answer_seller_info


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


class SellerInfoAnswerTests(unittest.TestCase):
    def test_city_answer_works_without_matching_product(self) -> None:
        storage = JSONAdapter(Path(tempfile.mkdtemp()))
        handler = MessageHandler(
            FailingLLM(),
            storage,
            seller={"city": "Iași"},
        )

        response = handler.process({
            "id": "seller_city",
            "text": "Din ce oraș sunteți?",
            "olx_conversation_id": "seller_city_conversation",
        })

        self.assertEqual(response, "Produsul se poate ridica personal din Iași.")

    def test_disabled_delivery_answer_works_without_matching_product(self) -> None:
        storage = JSONAdapter(Path(tempfile.mkdtemp()))
        handler = MessageHandler(
            FailingLLM(),
            storage,
            seller={
                "delivery_available": False,
                "courier": "Fan Courier",
            },
        )

        response = handler.process({
            "id": "seller_delivery",
            "text": "Trimiteți prin curier?",
            "olx_conversation_id": "seller_delivery_conversation",
        })

        self.assertEqual(response, "Nu se face livrare prin curier.")

    def test_payment_answer_works_without_matching_product(self) -> None:
        storage = JSONAdapter(Path(tempfile.mkdtemp()))
        handler = MessageHandler(
            FailingLLM(),
            storage,
            seller={"payment_methods": "numerar, transfer bancar"},
        )

        response = handler.process({
            "id": "seller_payment",
            "text": "Ce metode de plată acceptați?",
            "olx_conversation_id": "seller_payment_conversation",
        })

        self.assertEqual(
            response,
            "Metode de plată acceptate: numerar, transfer bancar.",
        )

    def test_missing_requested_seller_field_returns_none(self) -> None:
        self.assertIsNone(
            answer_seller_info(
                "Cu ce curier trimiteți?",
                {
                    "delivery_available": True,
                    "courier": "",
                },
            )
        )


class SellerInfoRegressionTests(unittest.TestCase):
    """Cazuri care au fost defecte o data — sa nu se intoarca."""

    CONFIGURAT = {
        "city": "Iasi",
        "pickup_available": True,
        "delivery_available": True,
        "courier": "FanCourier",
        "delivery_paid_by": "buyer",
        "payment_methods": "numerar, transfer",
    }

    def test_provenance_question_is_not_answered_with_our_city(self) -> None:
        """"De unde ai luat-o?" intreaba de unde ai CUMPARAT produsul, nu de
        unde se ridica. Botul raspundea cu orasul vanzatorului."""
        for question in (
            "Salut, de unde I-ai luat ?",
            "de unde ai cumparat-o?",
            "unde ai gasit asa ceva?",
        ):
            self.assertIsNone(answer_seller(question, self.CONFIGURAT), question)

    def test_unconfigured_seller_asserts_nothing(self) -> None:
        """delivery_available e False IMPLICIT — nu inseamna ca vanzatorul a
        spus ca nu trimite. Un cont nou refuza ferm livrarea unor cumparatori
        reali daca afirmam din valoarea implicita."""
        for question in ("trimiti prin curier?", "faci livrare?", "din ce oras esti?"):
            self.assertIsNone(answer_seller(question, {}), question)
        self.assertEqual(describe_seller({}), "")

    def test_natural_phrasings_are_recognised(self) -> None:
        """Potrivirea pe cuvant exact rata formele flexionate: "locatia",
        "transportul", "plateste"."""
        cases = {
            "Care este locatia?": "Iasi",
            "In ce localitate va aflati?": "Iasi",
            "Cine plateste transportul?": "cumpărător",
            "Cine suporta livrarea?": "cumpărător",
            "Ce metode de plata acceptati?": "numerar",
        }
        for question, expected in cases.items():
            self.assertIn(expected, answer_seller(question, self.CONFIGURAT) or "", question)

    def test_pickup_question_gets_a_yes_or_no(self) -> None:
        """Cu ridicarea dezactivata, "Vanzatorul este din Iasi" nu raspundea
        la intrebare si lasa impresia ca se poate ridica."""
        fara_ridicare = dict(self.CONFIGURAT, pickup_available=False)
        raspuns = answer_seller("pot sa ridic personal?", fara_ridicare)
        self.assertIsNotNone(raspuns)
        self.assertTrue(raspuns.lower().startswith("nu"), raspuns)

        fara_oras = dict(self.CONFIGURAT, city="")
        raspuns = answer_seller("pot ridica personal?", fara_oras)
        self.assertIsNotNone(raspuns)
        self.assertTrue(raspuns.lower().startswith("da"), raspuns)


if __name__ == "__main__":
    unittest.main()
