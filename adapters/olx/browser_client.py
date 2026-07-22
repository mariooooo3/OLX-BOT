"""Client Playwright pentru mesageria OLX.ro.

OLX nu are API public pentru mesaje, deci citirea/trimiterea se face prin
browser logat cu contul propriu.

IMPORTANT — autentificare:
OLX protejeaza login-ul cu un CAPTCHA anti-bot (slider "Glisați spre
dreapta"). Login-ul automat headless nu e posibil (si nici nu incercam
sa ocolim protectia). De aceea folosim un profil de browser persistent:

  1. O singura data, manual:  `python login.py`
     Se deschide o fereastra Chrome reala; te loghezi tu (rezolvi
     sliderul). Sesiunea se salveaza in profilul persistent.
  2. Apoi botul refoloseste acelasi profil, headless, deja logat.

Daca sesiunea expira, botul semnaleaza clar ca e nevoie de un nou
`python login.py`.

Selectorii OLX se pot schimba — sunt centralizati in SELECTORS.
"""
import random
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from loguru import logger
from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from adapters.olx.session_check import dom_logged_in, fetch_me
from core.faq_matcher import normalize_text
from core.response_formatter import sanitize_response

BASE_URL = "https://www.olx.ro"
# URL-ul paginii de mesaje se descopera la primul login manual si se
# salveaza; pana atunci, cel de mai jos e valoarea implicita.
# (vechiul /mesaje/ a fost retras de OLX si intoarce 404)
DEFAULT_CHAT_URL = f"{BASE_URL}/myaccount/answers/"

SELECTORS = {
    "cookie_accept": "#onetrust-accept-btn-handler",
    # lista de conversatii (/myaccount/answers/): fiecare item are testid
    # "conversations-list-item-<UUID>", unde UUID e id-ul conversatiei
    "conversation_list_item": "[data-testid^='conversations-list-item-']",
    # lista e impartita in sectiunile NECITITE / CITITE; itemii aflati
    # inaintea titlului CITITE sunt cei necititi
    "unread_section_title": "[data-testid='unread-section-title']",
    "read_section_title": "[data-testid='read-section-title']",
    # fallback daca sectiunile dispar: marker de necitit direct pe item
    "unread_marker": "[data-testid='unread-indicator'], .unread, [data-unread='true']",
    "received_message": "[data-testid='received-message']",
    "sent_message": "[data-testid='sent-message']",
    # bula cu textul mesajului (fara ora), in interiorul received/sent-message
    "message_bubble": "[data-cy='chat-message-bubble'], [data-testid='message']",
    # antetul conversatiei deschise: numele interlocutorului + titlul anuntului
    "conversation_user_name": "[data-testid='username']",
    "conversation_ad_title": "[data-testid='context-title'], [data-testid='context-details-title']",
    # taburile inboxului: "De vandut" (mesaje la anunturile mele) si
    # "De cumparat" (unde eu sunt cumparatorul). Cel activ are testid
    # 'tab-active'. Botul trebuie sa raspunda DOAR pe vanzari.
    "inbox_tab": "[data-testid='tab'], [data-testid='tab-active']",
    "reply_textarea": "textarea[name='message.text'], textarea",
    "send_button": "button[aria-label='Submit message'], button[type='submit']",
    # OLX tine butonul dezactivat pana cand React inregistreaza text in caseta;
    # asteptam varianta activa, altfel am da click pe un buton mort
    "send_button_enabled": (
        "button[aria-label='Submit message']:not([disabled]), "
        "button[type='submit']:not([disabled])"
    ),
}

CONVERSATION_ID_PREFIX = "conversations-list-item-"

class LoginRequiredError(RuntimeError):
    """Sesiunea OLX lipseste sau a expirat — e nevoie de `python login.py`."""


class ConversationClosedError(RuntimeError):
    """Conversatia nu accepta raspunsuri.

    OLX scoate caseta de raspuns cand interlocutorul si-a sters contul (apare
    ca "Utilizatorul nu exista") sau cand firul e inchis. Nu e o defectiune a
    botului si nu are rost reincercata — o sarim si mergem mai departe.
    """


def install_playwright_browsers() -> None:
    """`playwright install chromium` in acelasi mediu Python (venv).

    Binarele pot disparea intre rulari (upgrade playwright, tool de curatare
    disk, antivirus) — apelata automat cand lansarea browserului esueaza cu
    "Executable doesn't exist".
    """
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Reinstalarea browserelor Playwright a esuat: {output[-400:]}"
        )
    logger.info("Browsere Playwright instalate.")


class BrowserClient:
    def __init__(
        self,
        email: str = "",
        password: str = "",
        profile_dir: str | Path = "data/browser_profile",
        chat_url: str = DEFAULT_CHAT_URL,
        headless: bool = True,
    ):
        # email/password pastrate doar pentru compatibilitate; login-ul real
        # se face manual (CAPTCHA), nu cu credentialele de aici.
        self.email = email
        self.password = password
        self.profile_dir = Path(profile_dir)
        self.chat_url = chat_url
        self.headless = headless
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------------------------------------------------ #
    # ciclu de viata
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Porneste Chromium cu profilul persistent si verifica sesiunea."""
        logger.info("Pornesc browserul (headless={}).", self.headless)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            try:
                self._context = self._launch_context()
            except Exception as e:
                # binarele Playwright pot disparea intre rulari (upgrade de
                # playwright, tool de curatare disk, antivirus) — le
                # reinstalam automat si reincercam o singura data
                if "Executable doesn't exist" not in str(e):
                    raise
                logger.warning(
                    "Browserele Playwright lipsesc — le descarc automat "
                    "(poate dura cateva minute la prima rulare)..."
                )
                install_playwright_browsers()
                self._context = self._launch_context()
        except Exception:
            # nu lasam procesul driver Playwright orfan daca pornirea esueaza
            self.stop()
            raise
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else self._context.new_page()
        )

        if not self.is_logged_in():
            raise LoginRequiredError(
                "Sesiune OLX inexistenta sau expirata. Ruleaza `python login.py` "
                "si logheaza-te manual o singura data (OLX cere rezolvarea unui "
                "CAPTCHA slider la login)."
            )
        logger.info("Sesiune OLX valida — sunt logat.")

    def _launch_context(self) -> BrowserContext:
        return self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            locale="ro-RO",
            viewport={"width": 1366, "height": 850},
            args=["--disable-blink-features=AutomationControlled"],
        )

    def stop(self) -> None:
        """Idempotent si tolerant la un browser deja crapat, ca procesul
        Playwright sa nu ramana orfan daca inchiderea contextului esueaza."""
        logger.info("Opresc browserul.")
        try:
            if self._context:
                self._context.close()
        except Exception as e:
            logger.warning("Inchiderea contextului a esuat: {}", e)
        finally:
            self._context = None
            self._page = None
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception as e:
                    logger.warning("Oprirea Playwright a esuat: {}", e)
                self._playwright = None

    # ------------------------------------------------------------------ #
    # autentificare
    # ------------------------------------------------------------------ #

    def is_logged_in(self) -> bool:
        """Verificare in doua trepte: API-ul users/me (stabil, fara navigare),
        apoi fallback pe pagina /myaccount/ (vezi session_check)."""
        if fetch_me(self._context) is not None:
            return True
        # cookie-ul access_token expira intre rulari si e reimprospatat de
        # pagina abia dupa o navigare — la pornire "rece" users/me poate
        # esua desi sesiunea e valida; incalzim sesiunea pe homepage
        logger.debug("users/me nu a confirmat — incalzesc sesiunea pe homepage.")
        try:
            self._page.goto(BASE_URL, wait_until="domcontentloaded")
            self._page.wait_for_timeout(4000)
        except Exception:
            pass
        if fetch_me(self._context) is not None:
            return True
        logger.debug("users/me nu a confirmat nici dupa homepage — fallback DOM.")
        return dom_logged_in(self._page)

    def _accept_cookies(self) -> None:
        try:
            self._page.click(SELECTORS["cookie_accept"], timeout=3000)
        except Exception:
            pass  # bannerul nu e mereu prezent

    # ------------------------------------------------------------------ #
    # citire mesaje
    # ------------------------------------------------------------------ #

    def conversation_url(self, olx_conversation_id: str) -> str:
        """URL-ul unei conversatii: lista e la /myaccount/answers/, dar o
        conversatie e la /myaccount/answer/<UUID>/ (singular)."""
        base = self.chat_url.rstrip("/")
        if base.endswith("/answers"):
            base = base[: -len("/answers")] + "/answer"
        return f"{base}/{olx_conversation_id}/"

    def _unread_conversation_ids(self) -> list[str]:
        """Id-urile conversatiilor din sectiunea NECITITE a listei.

        Itemii dintre titlurile NECITITE si CITITE sunt cei necititi; daca
        titlurile de sectiune lipsesc, cadem pe markerul de necitit per item.
        """
        return self._page.evaluate(
            """([itemSel, unreadTitleSel, readTitleSel, markerSel, prefix]) => {
                const items = [...document.querySelectorAll(itemSel)];
                const toId = el => el.getAttribute('data-testid').slice(prefix.length);
                const unreadTitle = document.querySelector(unreadTitleSel);
                const readTitle = document.querySelector(readTitleSel);
                if (unreadTitle || readTitle) {
                    return items.filter(el => {
                        const afterUnread = !unreadTitle || Boolean(
                            unreadTitle.compareDocumentPosition(el)
                            & Node.DOCUMENT_POSITION_FOLLOWING
                        );
                        const beforeRead = !readTitle || Boolean(
                            readTitle.compareDocumentPosition(el)
                            & Node.DOCUMENT_POSITION_PRECEDING
                        );
                        return afterUnread && beforeRead;
                    }).map(toId);
                }
                return items
                    .filter(el => el.querySelector(markerSel))
                    .map(toId);
            }""",
            [
                SELECTORS["conversation_list_item"],
                SELECTORS["unread_section_title"],
                SELECTORS["read_section_title"],
                SELECTORS["unread_marker"],
                CONVERSATION_ID_PREFIX,
            ],
        )

    def _selling_inbox_url(self) -> str:
        """Forteaza filtrul OLX pentru mesajele primite la anunturile proprii."""
        parsed = urlparse(self.chat_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["my_ads"] = ["1"]
        return parsed._replace(query=urlencode(query, doseq=True)).geturl()

    def _ensure_selling_tab(self) -> bool:
        """Selecteaza tabul "De vandut" din inbox.

        Parametrul my_ads=1 din URL nu are niciun efect (verificat: lista e
        identica cu si fara el) — separarea se face doar din taburile paginii.
        Fara pasul asta, botul citeste orice tab a ramas activ si poate
        raspunde pe conversatii in care utilizatorul e CUMPARATOR.

        Intoarce True daca tabul de vanzari e activ.
        """
        page = self._page
        try:
            page.wait_for_selector(SELECTORS["inbox_tab"], timeout=10000)
        except PlaywrightTimeoutError:
            logger.warning(
                "Nu am gasit taburile inboxului — citesc lista asa cum e."
            )
            return False

        for tab in page.query_selector_all(SELECTORS["inbox_tab"]):
            eticheta = normalize_text(tab.inner_text() or "")
            if "vandut" not in eticheta:
                continue
            if tab.get_attribute("data-testid") == "tab-active":
                logger.debug("Tabul 'De vandut' e deja activ.")
                return True
            logger.info("Comut pe tabul 'De vandut' (era pe cumparari).")
            tab.click()
            self._human_pause(1.5, 3)
            return True

        logger.warning("Tabul 'De vandut' nu a fost gasit in inbox.")
        return False

    def _conversation_ids_to_scan(self) -> list[str]:
        """Doar conversatiile marcate NECITITE de OLX, in ordinea din inbox."""
        return self._unread_conversation_ids()

    def _latest_received_message_text(self) -> str | None:
        """Textul ultimei bule doar daca ea a fost primita de contul curent."""
        messages = self._page.query_selector_all(
            f"{SELECTORS['received_message']}, {SELECTORS['sent_message']}"
        )
        if not messages:
            return None
        latest = messages[-1]
        if latest.get_attribute("data-testid") != "received-message":
            return None
        bubble = latest.query_selector(SELECTORS["message_bubble"])
        text = ((bubble or latest).inner_text() or "").strip()
        return text or None

    def _header_text(self, selector_key: str) -> str | None:
        """Textul unui element din antetul conversatiei deschise (sau None)."""
        try:
            el = self._page.query_selector(SELECTORS[selector_key])
            text = (el.inner_text() or "").strip() if el else ""
            return text or None
        except Exception:
            return None

    def _message_from_open_conversation(self, conv_id: str) -> dict | None:
        """Construieste mesajul doar daca OLX permite raspunsul la anunt."""
        ad_title = self._header_text("conversation_ad_title")
        title_status = ad_title.split(maxsplit=1)[0].strip().casefold() if ad_title else ""
        if title_status == "inactiv":
            logger.info(
                "Ignor conversatia {}: anuntul este inactiv, iar OLX nu permite raspunsuri.",
                conv_id,
            )
            return None

        last_text = self._latest_received_message_text()
        if not last_text:
            return None
        return {
            "id": f"olx_{conv_id}",
            "text": last_text,
            "olx_conversation_id": conv_id,
            "buyer_name": self._header_text("conversation_user_name"),
            "ad_title": ad_title,
        }

    def get_new_messages(self) -> list[dict]:
        """Returneaza mesajele noi din inbox-ul de vanzari OLX.

        Format: [{"id", "text", "olx_conversation_id", "buyer_name", "ad_title"}]
        """
        page = self._page
        page.goto(self._selling_inbox_url(), wait_until="domcontentloaded")
        self._human_pause(2, 4)
        # separarea vanzari/cumparari se face din taburi, nu din URL
        self._ensure_selling_tab()
        try:
            # chatul e un SPA — lista apare dupa incarcarea initiala
            page.wait_for_selector(
                f"{SELECTORS['conversation_list_item']}, "
                f"{SELECTORS['unread_section_title']}",
                timeout=15000,
            )
        except Exception:
            logger.debug("Lista de conversatii nu a aparut (inbox gol?).")

        total = len(page.query_selector_all(SELECTORS["conversation_list_item"]))
        conversation_ids = self._conversation_ids_to_scan()
        logger.info(
            "{} conversatii in inbox-ul de vanzari; verific {} candidate.",
            total,
            len(conversation_ids),
        )

        messages: list[dict] = []
        for conv_id in conversation_ids:
            page.goto(
                self.conversation_url(conv_id), wait_until="domcontentloaded"
            )
            self._human_pause(1.5, 3)

            try:
                page.wait_for_selector(
                    f"{SELECTORS['received_message']}, {SELECTORS['sent_message']}",
                    timeout=10000,
                )
            except Exception:
                logger.debug("Conversatia {} nu contine bule de mesaj.", conv_id)
                continue
            message = self._message_from_open_conversation(conv_id)
            if message:
                messages.append(message)

        logger.info("{} mesaje noi gasite.", len(messages))
        return messages

    # ------------------------------------------------------------------ #
    # trimitere raspuns
    # ------------------------------------------------------------------ #

    def send_reply(self, olx_conversation_id: str, text: str) -> None:
        """Deschide conversatia, scrie raspunsul si trimite cu delay uman."""
        page = self._page
        text = sanitize_response(text)
        if not text:
            raise ValueError("Raspunsul este gol dupa curatare; nu trimit mesajul.")
        page.goto(
            self.conversation_url(olx_conversation_id),
            wait_until="domcontentloaded",
        )
        self._human_pause(1.5, 3)

        box = self._reply_box()
        self._write_reply(box, text)

        # delay random 3-8 sec inainte de trimitere (obligatoriu, comportament uman)
        self._human_pause(3, 8)

        try:
            # asteptam ca butonul sa devina ACTIV, nu doar sa existe: OLX il
            # tine dezactivat cat timp nu inregistreaza text in caseta
            page.wait_for_selector(SELECTORS["send_button_enabled"], timeout=10000)
            page.click(SELECTORS["send_button_enabled"])
        except PlaywrightTimeoutError:
            # unele variante de chat trimit cu Enter; incercam inainte sa cedam
            logger.warning("Butonul de trimitere e dezactivat — incerc cu Enter.")
            box.press("Enter")
            self._human_pause(1, 2)
            if self._box_text(box):
                raise RuntimeError(
                    f"Nu am putut trimite raspunsul in conversatia "
                    f"{olx_conversation_id}: butonul de trimitere a ramas "
                    "dezactivat si Enter nu a golit caseta. Cel mai probabil "
                    "conversatia nu accepta raspunsuri (anunt inactiv sau cont "
                    "sters), altfel OLX si-a schimbat interfata de chat."
                ) from None
        logger.info("Raspuns trimis in conversatia {}.", olx_conversation_id)
        self._human_pause(1, 2)

    def _reply_box(self):
        """Caseta de raspuns.

        Preferam selectorul specific: cel generic ('textarea') poate nimeri
        alt camp din pagina, iar atunci am scrie in gol si butonul de
        trimitere ar ramane dezactivat fara motiv aparent.
        """
        page = self._page
        try:
            page.wait_for_selector(SELECTORS["reply_textarea"], timeout=15000)
        except PlaywrightTimeoutError:
            raise ConversationClosedError(
                "Conversatia nu are caseta de raspuns — cel mai probabil "
                "utilizatorul si-a sters contul sau firul e inchis."
            ) from None
        specific = page.locator("textarea[name='message.text']")
        if specific.count():
            return specific.first
        logger.debug("Caseta de raspuns gasita doar prin selectorul generic.")
        return page.locator(SELECTORS["reply_textarea"]).first

    def _write_reply(self, box, text: str) -> None:
        """Scrie textul in caseta si confirma ca a ajuns acolo.

        Tastam caracter cu caracter (nu page.fill): asa emitem keydown/input
        ca de la tastatura, ceea ce e si mai aproape de comportamentul uman.
        Verificam rezultatul si reincercam o data — pagina poate fi inca in
        curs de hidratare imediat dupa navigare, caz in care primele taste se
        pierd si caseta ramane goala.
        """
        for attempt in (1, 2):
            box.click()
            box.press("Control+a")
            box.press("Backspace")
            box.press_sequentially(text, delay=random.uniform(25, 55))
            if self._box_text(box):
                return
            logger.warning(
                "Caseta de raspuns a ramas goala dupa tastare (incercarea {}).",
                attempt,
            )
            self._human_pause(1, 2)
        raise RuntimeError(
            "Nu am putut scrie raspunsul in caseta de chat — pagina nu a "
            "raspuns la tastare."
        )

    @staticmethod
    def _box_text(box) -> str:
        """Textul din caseta; gol inseamna ca mesajul a plecat."""
        try:
            return (box.input_value() or "").strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------ #
    # utilitare
    # ------------------------------------------------------------------ #

    @staticmethod
    def _human_pause(min_s: float, max_s: float) -> None:
        time.sleep(random.uniform(min_s, max_s))
