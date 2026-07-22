import uuid
import re
import unicodedata
from datetime import datetime, timezone

from loguru import logger

from adapters.llm.base import BaseLLMAdapter
from adapters.storage.base import BaseStorageAdapter
from core.fallback_catalog import detect_category
from core.faq_matcher import FAQMatcher
from core.product_matcher import match_product
from core.product_schema import describe_vat, migrate_product
from core.prompt_builder import build_system_prompt, build_user_prompt
from core.response_formatter import fallback_response, format_response


def _normalize_question(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _negotiable_response(buyer_message: str, product: dict) -> str | None:
    """Raspuns determinist la "e negociabil?".

    E cea mai frecventa intrebare de pe OLX si tocmai cea la care potrivirea
    semantica gresea (raspundea despre negociere cuiva care intrebase pretul).
    Ca bifa pe produs, raspunsul nu mai depinde de niciun prag.
    """
    question = _normalize_question(buyer_message)
    if not re.search(r"\b(negocia\w*|discuta\w*|lasi|last|oferta)\b", question):
        return None
    # "cat costa" / "care e pretul" NU sunt intrebari despre negociere
    if re.search(r"\b(cat costa|care (e|este) pretul)\b", question):
        return None
    if product.get("negotiable"):
        return "Da, prețul este negociabil."
    return "Nu, prețul nu este negociabil."


def _vat_response(buyer_message: str, product: dict) -> str | None:
    """Raspuns determinist despre TVA si factura.

    Suma cu TVA e CALCULATA, nu compusa de model — o cifra gresita aici
    inseamna bani pierduti.
    """
    question = _normalize_question(buyer_message)
    if not re.search(r"\b(tva|factura|facturi|deduc\w*)\b", question):
        return None
    # NU .capitalize(): ar lowercase-ui restul textului si ar strica "TVA"/"RON"
    text = describe_vat(product)
    return text[:1].upper() + text[1:] + "."


def _warranty_response(buyer_message: str, product: dict) -> str | None:
    """Raspuns determinist despre garantie."""
    question = _normalize_question(buyer_message)
    if not re.search(r"\bgarantie\b", question):
        return None
    warranty = str(product.get("warranty") or "").strip()
    if not warranty:
        return None  # necompletat: lasam LLM-ul sa formuleze prudent
    if re.fullmatch(r"(nu|fara|niciuna|0)", _normalize_question(warranty)):
        return "Produsul nu are garanție."
    return f"Produsul are garanție: {warranty}."


def _certain_answer(buyer_message: str, product: dict) -> str | None:
    """Primul raspuns determinist care se aplica (negociere, TVA, garantie).

    Folosit doar dupa ce FAQ-ul nu a acoperit intrebarea: raspunsul scris de
    vanzator are mereu prioritate fata de formularea generica a botului.
    """
    for rule in (_negotiable_response, _vat_response, _warranty_response):
        answer = rule(buyer_message, product)
        if answer:
            return answer
    return None


def _availability_response(buyer_message: str, stock: object) -> str | None:
    """Raspuns determinist pentru intrebarile despre disponibilitate."""
    question = _normalize_question(buyer_message)
    # "cate/cati" singur nu e suficient ("cate viteze are?" e despre produs,
    # nu despre stoc) — cere si o referinta la stoc/bucati/produse, sau
    # forma scurta "cate mai ai/aveti"
    quantity_question = bool(
        (
            re.search(r"\b(?:cate|cati)\b", question)
            and re.search(r"\b(?:stoc|bucat\w*|produs\w*|ramas\w*)\b", question)
        )
        or re.fullmatch(r"(?:cate|cati) mai (?:ai|aveti|sunt|este)", question)
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
    """Orchestreaza fluxul: matching produs -> stoc determinist -> FAQ
    semantic (raspuns direct la potrivire puternica) -> LLM (doar la
    nevoie) -> validare, cu fallback categorisit cand totul esueaza.

    Nu stie nimic de Groq sau JSON — primeste adaptoarele prin constructor,
    deci la MVP2 ramane neschimbat.
    """

    def __init__(
        self,
        llm: BaseLLMAdapter,
        storage: BaseStorageAdapter,
        embeddings=None,
        seller: dict | None = None,
    ):
        self.llm = llm
        self.storage = storage
        self.faq_matcher = FAQMatcher(embeddings)
        # locatie, livrare, plata — comune tuturor anunturilor contului
        self.seller = seller or {}

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

        products = [migrate_product(p) for p in self.storage.get_products()]
        # titlul anuntului identifica exact produsul discutat (potrivire
        # stricta pe titlu); fara el, euristica pe cuvinte cheie
        product = match_product(
            buyer_message, products, ad_title=message.get("ad_title")
        )
        # ultimul raspuns trimis in conversatie — fallback-ul nu se repeta
        last_response = self._last_bot_response(olx_conversation_id)

        # Stocul are prioritate chiar si peste FAQ: numarul din catalog e
        # autoritatea, iar un FAQ scris candva ("mai am 3 bucati") se
        # invecheste. Restul regulilor deterministe vin DUPA FAQ — daca
        # vanzatorul a scris un raspuns, cuvintele lui conteaza mai mult
        # decat o propozitie generica a botului.
        stock_answer = (
            _availability_response(buyer_message, product.get("stock"))
            if product is not None
            else None
        )

        if product is None:
            logger.warning("Niciun produs potrivit — folosesc fallback.")
            response = fallback_response(
                avoid=last_response,
                category=detect_category(buyer_message, self.faq_matcher),
            )
        elif stock_answer is not None:
            response = format_response(stock_answer, avoid=last_response)
        else:
            faq = self.faq_matcher.best_match(buyer_message, product.get("faq"))
            if faq is not None and faq.direct:
                # potrivire puternica: raspunsul scris de vanzator se
                # trimite ca atare — fara LLM, zero halucinatie
                logger.info(
                    "Raspuns direct din FAQ (scor {:.2f}): {!r}",
                    faq.score, faq.question,
                )
                response = format_response(faq.answer, avoid=last_response)
            elif (certain := _certain_answer(buyer_message, product)) is not None:
                # niciun FAQ nu acopera intrebarea, dar avem faptul in catalog:
                # raspundem exact, fara sa mai riscam o formulare de model
                logger.info("Raspuns determinist din datele produsului.")
                response = format_response(certain, avoid=last_response)
            else:
                hint = (faq.question, faq.answer) if faq is not None else None
                system_prompt = build_system_prompt()
                user_prompt = build_user_prompt(
                    product, buyer_message, faq_hint=hint, seller=self.seller
                )
                try:
                    raw_response = self.llm.generate_reply(system_prompt, user_prompt)
                except Exception as e:
                    logger.error("Eroare LLM: {} — folosesc fallback.", e)
                    raw_response = ""
                response = format_response(
                    raw_response,
                    avoid=last_response,
                    category=detect_category(buyer_message, self.faq_matcher),
                )

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
