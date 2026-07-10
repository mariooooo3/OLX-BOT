import uuid
import re
import unicodedata
from datetime import datetime, timezone

from loguru import logger

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.base import BaseStorageAdapter
from core.product_matcher import match_product
from core.prompt_builder import build_system_prompt, build_user_prompt
from core.response_formatter import fallback_response, format_response


def _normalize_question(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _availability_response(buyer_message: str, stock: object) -> str | None:
    """Raspuns determinist pentru intrebarile despre disponibilitate."""
    question = _normalize_question(buyer_message)
    quantity_question = bool(
        re.search(r"\b(?:cate|cati)\b", question)
        or re.fullmatch(r"ce stoc(?: mai (?:aveti|ai))?", question)
    )
    try:
        stock_number = float(stock)
    except (TypeError, ValueError):
        stock_number = None

    if quantity_question:
        if stock_number is None:
            return "Stocul nu este specificat."
        stock_text = str(int(stock_number)) if stock_number.is_integer() else str(stock_number)
        if stock_number == 1:
            return "Mai este 1 produs în stoc."
        if stock_number <= 0:
            return "Nu mai sunt produse în stoc."
        return f"Mai sunt {stock_text} produse în stoc."

    explicit = any(term in question for term in ("disponibil", "pe stoc", "in stoc"))
    generic = bool(
        re.fullmatch(r"(?:produsul )?mai (?:este|e)(?: disponibil| pe stoc)?", question)
        or re.fullmatch(r"(?:produsul )?se poate", question)
        or re.fullmatch(r"(?:il |o )?mai (?:aveti|ai)", question)
    )
    if not explicit and not generic:
        return None

    available = stock_number is not None and stock_number > 0
    if not available:
        return "Nu, produsul nu mai este disponibil."
    if "stoc" in question or question.startswith("mai "):
        return "Da, mai este în stoc."
    return "Da, produsul este disponibil."


class MessageHandler:
    """Orchestreaza fluxul: matching produs -> prompt -> LLM -> validare.

    Nu stie nimic de Groq sau JSON — primeste adaptoarele prin constructor,
    deci la MVP2 ramane neschimbat.
    """

    def __init__(self, llm: BaseLLMAdapter, storage: BaseStorageAdapter):
        self.llm = llm
        self.storage = storage

    def process(self, message: dict) -> str | None:
        """Proceseaza un mesaj nou si returneaza raspunsul de trimis.

        message: {"id", "text", "olx_conversation_id", ...}
        Returneaza None daca mesajul a fost deja procesat.
        """
        olx_conversation_id = message["olx_conversation_id"]
        buyer_message = message["text"]

        if self.storage.is_processed(olx_conversation_id, buyer_message):
            logger.info(
                "Mesajul din conversatia {} e deja procesat — sar.",
                olx_conversation_id,
            )
            return None

        logger.info("Procesez mesaj din conversatia {}: {!r}",
                    olx_conversation_id, buyer_message)

        products = self.storage.get_products()
        # titlul anuntului identifica exact produsul discutat (potrivire
        # stricta pe titlu); fara el, euristica pe cuvinte cheie
        product = match_product(
            buyer_message, products, ad_title=message.get("ad_title")
        )
        # ultimul raspuns trimis in conversatie — fallback-ul nu se repeta
        last_response = self._last_bot_response(olx_conversation_id)

        availability = (
            _availability_response(buyer_message, product.get("stock"))
            if product is not None
            else None
        )

        if product is None:
            logger.warning("Niciun produs potrivit — folosesc fallback.")
            response = fallback_response(avoid=last_response)
        elif availability is not None:
            response = format_response(availability, avoid=last_response)
        else:
            system_prompt = build_system_prompt()
            user_prompt = build_user_prompt(product, buyer_message)
            try:
                raw_response = self.llm.generate_reply(system_prompt, user_prompt)
            except Exception as e:
                logger.error("Eroare LLM: {} — folosesc fallback.", e)
                raw_response = ""
            response = format_response(raw_response, avoid=last_response)

        self.storage.log_conversation({
            "id": f"conv_{uuid.uuid4().hex[:8]}",
            "olx_conversation_id": olx_conversation_id,
            "product_id": product.get("id") if product else None,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "buyer_message": buyer_message,
            "bot_response": response,
            # Trimiterea efectiva este facuta ulterior de BrowserClient.
            # Doar expeditorul poate confirma statusul "sent".
            "status": "pending",
            # cine a scris si la ce anunt — pentru firul din dashboard
            "buyer_name": message.get("buyer_name"),
            "ad_title": message.get("ad_title"),
        })

        return response

    def _last_bot_response(self, olx_conversation_id: str) -> str | None:
        """Ultimul raspuns trimis in conversatie (None daca nu exista)."""
        try:
            entries = [
                c for c in self.storage.get_conversations()
                if c.get("olx_conversation_id") == olx_conversation_id
            ]
            return entries[-1].get("bot_response") if entries else None
        except Exception:
            return None  # adaptor fara istoric — fallback fara restrictie
