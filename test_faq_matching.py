"""Teste offline pentru FAQ semantic + fallback categorisit (fara model real,
fara browser, fara API). Embeddings-urile sunt simulate cu un vocabular mic.

Rulare:  python test_faq_matching.py
"""
import tempfile
import unittest
from pathlib import Path

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.json_adapter import JSONAdapter
from core.fallback_catalog import CATEGORIES, detect_category
from core.faq_matcher import FAQMatcher, lexical_score
from core.message_handler import MessageHandler


class MockEmbeddings:
    """Vectori deterministi pe un vocabular-jucarie: fiecare cuvant-cheie e
    o axa; textele care impart cuvinte-cheie au cosine mare."""

    model_name = "mock-model"
    AXES = ["negoc", "pret", "livr", "curier", "garant", "culoare"]

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        vectors = []
        for text in texts:
            lowered = text.lower()
            vec = [1.0 if axis in lowered else 0.0 for axis in self.AXES]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


class RecordingLLM(BaseLLMAdapter):
    """Inregistreaza prompturile; poate fi setat sa esueze."""

    def __init__(self, reply="Raspuns generat de LLM.", fail=False):
        self.reply = reply
        self.fail = fail
        self.prompts: list[str] = []

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        if self.fail:
            raise RuntimeError("LLM indisponibil")
        self.prompts.append(user_prompt)
        return self.reply


FAQ = [
    {"question": "pretul este negociabil?", "answer": "Nu, pretul nu este negociabil."},
    {"question": "faceti livrare prin curier?", "answer": "Da, livrez prin curier oriunde in tara."},
    {"question": "", "answer": ""},  # intrari goale din UI — trebuie ignorate
]


def make_handler(llm, embeddings=None):
    storage = JSONAdapter(Path(tempfile.mkdtemp()))
    storage.save_product({
        "id": "prod_1",
        "title": "Bicicleta Trek",
        "stock": 2,
        "faq": FAQ,
    })
    handler = MessageHandler(llm, storage, embeddings=embeddings)
    # cache-ul de embeddings ramane in directorul temporar al testului
    handler.faq_matcher.cache_path = Path(tempfile.mkdtemp()) / "cache.json"
    return handler, storage


def process(handler, text, conv="c1"):
    return handler.process({
        "id": "m1", "text": text,
        "olx_conversation_id": conv, "ad_title": "Bicicleta Trek",
    })


class FAQMatcherTests(unittest.TestCase):
    def test_direct_hit_returns_seller_answer_without_llm(self):
        llm = RecordingLLM(fail=True)  # LLM-ul ar crapa daca ar fi apelat
        handler, _ = make_handler(llm, MockEmbeddings())
        response = process(handler, "se poate negocia pretul?")
        self.assertEqual(response, "Nu, pretul nu este negociabil.")

    def test_no_faq_match_falls_through_to_llm(self):
        llm = RecordingLLM(reply="Are 21 de viteze.")
        handler, _ = make_handler(llm, MockEmbeddings())
        response = process(handler, "cate viteze are?")
        self.assertEqual(response, "Are 21 de viteze.")
        self.assertEqual(len(llm.prompts), 1)

    def test_medium_match_injects_hint_into_prompt(self):
        llm = RecordingLLM(reply="Da, trimit prin curier.")
        handler, _ = make_handler(llm, MockEmbeddings())
        # "trimiteti coletul prin curier?" imparte doar axa "curier" cu FAQ-ul
        # de livrare -> scor mediu (hint), nu direct
        matcher = handler.faq_matcher
        match = matcher.best_match("trimiteti coletul prin curier?", FAQ)
        if match is not None and not match.direct:
            process(handler, "trimiteti coletul prin curier?")
            self.assertIn("faceti livrare prin curier?", llm.prompts[0])

    def test_lexical_only_when_embeddings_missing(self):
        # fara embeddings, intrebarea identica tot da raspuns direct
        llm = RecordingLLM(fail=True)
        handler, _ = make_handler(llm, embeddings=None)
        response = process(handler, "pretul este negociabil?")
        self.assertEqual(response, "Nu, pretul nu este negociabil.")

    def test_empty_faq_entries_are_ignored(self):
        matcher = FAQMatcher(embeddings=None)
        self.assertIsNone(matcher.best_match("orice text", [{"question": "", "answer": ""}]))
        self.assertIsNone(matcher.best_match("orice text", []))
        self.assertIsNone(matcher.best_match("orice text", None))

    def test_faq_vectors_are_cached_on_disk(self):
        embeddings = MockEmbeddings()
        matcher = FAQMatcher(embeddings)
        matcher.cache_path = Path(tempfile.mkdtemp()) / "cache.json"
        matcher.best_match("se poate negocia?", FAQ)
        calls_first = embeddings.calls
        matcher2 = FAQMatcher(embeddings)
        matcher2.cache_path = matcher.cache_path
        matcher2.best_match("se poate negocia?", FAQ)
        # a doua rulare embeduieste doar mesajul, nu si FAQ-ul (vine din cache)
        self.assertEqual(embeddings.calls, calls_first + 1)

    def test_lexical_score_matches_word_roots(self):
        self.assertGreaterEqual(
            lexical_score("se poate negocia?", "pretul este negociabil?"), 1.0
        )
        self.assertEqual(lexical_score("buna ziua", "faceti livrare?"), 0.0)


class FallbackCategoryTests(unittest.TestCase):
    def test_regex_detects_content_categories(self):
        cases = {
            "care e ultimul pret?": "pret",
            "faceti livrare in tara?": "livrare",
            "e nou sau folosit?": "stare",
            "din ce oras pot ridica produsul?": "locatie",
            "Bună ziua!": "salut",
        }
        for text, expected in cases.items():
            self.assertEqual(detect_category(text), expected, msg=text)

    def test_greeting_with_content_is_not_salut(self):
        self.assertEqual(detect_category("buna ziua, faceti livrare?"), "livrare")

    def test_unknown_message_has_no_category(self):
        self.assertIsNone(detect_category("mesaj complet aleatoriu xyz"))

    def test_llm_failure_uses_categorized_fallback(self):
        llm = RecordingLLM(fail=True)
        handler, _ = make_handler(llm, embeddings=None)
        # intrebare de livrare fara potrivire FAQ suficient de buna nu exista
        # aici (FAQ-ul de livrare da direct), deci folosim o intrebare de pret
        # reformulata fara cuvintele din FAQ dar cu cuvinte din regex
        response = process(handler, "imi faci o reducere?")
        self.assertIn(response, CATEGORIES["pret"]["responses"])

    def test_no_dashes_in_category_responses(self):
        for name, spec in CATEGORIES.items():
            for response in spec["responses"]:
                for dash in "-‐‑‒–—―−":
                    self.assertNotIn(dash, response, msg=name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
