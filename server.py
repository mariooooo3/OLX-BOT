"""API server pentru dashboard-ul web (ui/).

Expune peste botul existent:
  - CRUD produse        -> data/accounts/<cont>/products.json (JSONAdapter)
  - conversatii         -> data/accounts/<cont>/conversations.json
  - start/stop bot      -> cate un thread de polling per cont OLX (BotFleet),
                           deci mai multe conturi raspund in acelasi timp
  - setari              -> data/settings.json + suprascrieri per cont

Conturile sunt complet separate: profil de browser, date, setari si model LLM
propriu. Contul "activ" din data/accounts.json e doar lentila dashboard-ului
(ce produse/setari editezi), nu mai decide pe ce cont ruleaza botul.

Pornire:  uvicorn server:app --port 8000
"""
import itertools
import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

import config
from core.message_handler import MessageHandler
from core.product_schema import empty_product, migrate_product
from core.seller_info import DEFAULT_SELLER_INFO, normalize as normalize_seller

PROJECT_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = Path("data/settings.json")
# profilul unic din prima versiune + markerul lui — migrate automat la primul cont
LEGACY_PROFILE_DIR = Path("data/browser_profile")
LEGACY_MARKER_PATH = Path("data/olx_logged_in.json")
# fiecare cont OLX are propriul profil de browser => sesiuni complet separate
PROFILES_ROOT = Path("data/browser_profiles")
# datele fiecarui cont (produse, conversatii, setari) — izolate per cont,
# ca dashboard-ul sa arate strict informatiile contului activ
ACCOUNTS_DATA_ROOT = Path("data/accounts")
ACCOUNTS_PATH = Path("data/accounts.json")
# marker scris de login.py in profilul contului dupa un login confirmat
SESSION_MARKER_NAME = "olx_session.json"
DEFAULT_SETTINGS = {
    "poll_interval_seconds": config.POLL_INTERVAL_SECONDS,
    # backend-ul + modelul LLM, alese din dashboard (env doar ca implicit)
    "llm_backend": config.LLM_BACKEND,
    "groq_model": "llama-3.1-8b-instant",
    "ollama_model": config.OLLAMA_MODEL,
    "log_level": config.LOG_LEVEL,
    "olx_chat_url": "https://www.olx.ro/myaccount/answers/",
    # locatie / livrare / plata — aceleasi pentru toate anunturile contului,
    # deci se completeaza o data, nu la fiecare produs
    "seller_info": dict(DEFAULT_SELLER_INFO),
}

def _build_llm(settings: dict):
    """Construieste LLM-ul respectand backend-ul si modelul din setari."""
    return config.build_llm(settings)


def _apply_log_level(level: str) -> None:
    """Reconfigureaza loguru cu nivelul din setari (INFO/DEBUG) — setarea
    din dashboard se aplica imediat, nu doar la restartul serverului."""
    if level not in ("INFO", "DEBUG"):
        level = "INFO"
    logger.remove()
    logger.add(sys.stderr, level=level)
    logger.add("logs/bot.log", level=level,
               rotation="10 MB", retention="14 days", encoding="utf-8")


def load_settings(account: dict | None = None) -> dict:
    """Setarile efective ale unui cont: DEFAULT_SETTINGS + settings.json
    global + suprascrierile contului (implicit contul activ)."""
    merged = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        merged.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    account = account if account is not None else active_account()
    if account is not None:
        override_path = account_settings_path(account["id"])
        if override_path.exists():
            merged.update(json.loads(override_path.read_text(encoding="utf-8")))
    return merged


def save_settings(settings: dict, account: dict | None = None) -> None:
    """Scrie setarile contului dat (implicit cel activ); fara niciun cont,
    scrie in fisierul global."""
    account = account if account is not None else active_account()
    path = account_settings_path(account["id"]) if account else SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------- #
# conturi OLX — un profil de browser separat per cont
# --------------------------------------------------------------------- #

def load_accounts() -> dict:
    """{"active": id | None, "accounts": [{"id", "label", "profile_dir"}]}"""
    if ACCOUNTS_PATH.exists():
        return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    return {"active": None, "accounts": []}


def save_accounts(accounts: dict) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_PATH.write_text(
        json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def find_account(accounts: dict, account_id: str | None) -> dict | None:
    return next((a for a in accounts["accounts"] if a["id"] == account_id), None)


def active_account(accounts: dict | None = None) -> dict | None:
    accounts = accounts if accounts is not None else load_accounts()
    return find_account(accounts, accounts.get("active"))


def marker_path(account: dict) -> Path:
    return Path(account["profile_dir"]) / SESSION_MARKER_NAME


def account_data_dir(account_id: str) -> Path:
    return ACCOUNTS_DATA_ROOT / account_id


def account_settings_path(account_id: str) -> Path:
    return account_data_dir(account_id) / "settings.json"


def account_storage(account: dict | None = None):
    """Stocarea (produse + conversatii) contului dat sau a celui activ.

    Fiecare cont are datele lui in data/accounts/<id>/ — dashboard-ul arata
    strict informatiile contului activ. None daca nu exista niciun cont.
    """
    account = account if account is not None else active_account()
    if account is None:
        return None
    return config.build_storage(account["id"])


def accounts_in_scope(account_id: str | None) -> list[dict]:
    """Conturile vizate de o cerere de citire.

    Fara account_id (sau "all") = toate conturile: dashboard-ul insumeaza
    activitatea, fiindca botul raspunde pe toate deodata. Cu un id anume =
    doar contul acela (filtrul din UI).
    """
    accounts = load_accounts()["accounts"]
    if account_id in (None, "", "all"):
        return accounts
    account = next((a for a in accounts if a["id"] == account_id), None)
    if account is None:
        raise HTTPException(status_code=404, detail="Cont inexistent")
    return [account]


def conversations_in_scope(account_id: str | None) -> list[dict]:
    """Conversatiile conturilor vizate, fiecare marcata cu contul ei."""
    entries = []
    for account in accounts_in_scope(account_id):
        storage = config.build_storage(account["id"])
        for entry in storage.get_conversations():
            entries.append(
                entry
                | {
                    "account_id": account["id"],
                    "account_label": account_display_name(account),
                }
            )
    return entries


def account_connected(account: dict) -> bool:
    """Conectat = login.py a confirmat un login reusit pentru acest profil.
    Nu folosim doar existenta profilului: Chromium creeaza fisiere de profil
    la orice lansare, chiar fara login."""
    return marker_path(account).exists()


def read_marker(account: dict) -> dict:
    try:
        return json.loads(marker_path(account).read_text(encoding="utf-8"))
    except Exception:
        return {}


# Cate culori distincte are paleta din UI. Indexul e alocat la crearea
# contului si salvat in accounts.json: stergerea unui cont nu reamesteca
# culorile celorlalte, asa ca "verde = Mario" ramane adevarat in timp.
ACCOUNT_COLORS = 8


def account_color(account: dict, accounts: dict | None = None) -> int:
    """Indexul de culoare al contului (0..ACCOUNT_COLORS-1).

    Conturile create inainte de paleta nu au campul salvat — le dam un index
    din pozitia in registru, stabil cat timp lista nu se schimba.
    """
    if isinstance(account.get("color"), int):
        return account["color"] % ACCOUNT_COLORS
    accounts = accounts if accounts is not None else load_accounts()
    ids = [a["id"] for a in accounts["accounts"]]
    position = ids.index(account["id"]) if account["id"] in ids else 0
    return position % ACCOUNT_COLORS


def _next_color(accounts: dict) -> int:
    """Prima culoare nefolosita, ca doua conturi noi sa nu arate la fel."""
    used = {a["color"] for a in accounts["accounts"] if isinstance(a.get("color"), int)}
    return next(
        (c for c in range(ACCOUNT_COLORS) if c not in used),
        len(accounts["accounts"]) % ACCOUNT_COLORS,
    )


def account_info(account: dict, accounts: dict | None = None) -> dict:
    """Descrierea unui cont folosita peste tot in UI (selector de scope,
    etichete pe mesaje/produse, comutatoare)."""
    marker = read_marker(account)
    return {
        "id": account["id"],
        "label": account["label"],
        # emailul + numele contului OLX, salvate de login.py (users/me)
        "username": marker.get("username"),
        "name": marker.get("name"),
        "display_name": account_display_name(account),
        "color": account_color(account, accounts),
        "connected": account_connected(account),
    }


def account_display_name(account: dict) -> str:
    """Cum se numeste contul in dashboard: numele/emailul OLX detectat la
    login, altfel eticheta locala ("Cont 2"). Cu mai multe conturi active,
    "Cont 2" nu spune nimic — numele real da."""
    marker = read_marker(account)
    return marker.get("name") or marker.get("username") or account["label"]


def create_account(accounts: dict, label: str | None = None) -> dict:
    account_id = f"acc_{uuid.uuid4().hex[:6]}"
    label = (label or "").strip() or f"Cont {len(accounts['accounts']) + 1}"
    profile_dir = PROFILES_ROOT / account_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    account = {
        "id": account_id,
        "label": label,
        "profile_dir": str(profile_dir),
        "color": _next_color(accounts),
    }
    accounts["accounts"].append(account)
    if accounts.get("active") is None:
        accounts["active"] = account_id
    save_accounts(accounts)
    # daca exista date globale din versiunile vechi, devin ale primului cont
    migrate_global_data_to_account()
    return account


def migrate_legacy_profile() -> None:
    """Profilul unic din versiunile vechi devine primul cont din registru."""
    accounts = load_accounts()
    if accounts["accounts"] or not LEGACY_PROFILE_DIR.exists():
        return
    account = {
        "id": "acc_default",
        "label": "Cont 1",
        "profile_dir": str(LEGACY_PROFILE_DIR),
    }
    if LEGACY_MARKER_PATH.exists():
        marker = json.loads(LEGACY_MARKER_PATH.read_text(encoding="utf-8"))
        marker.setdefault("chat_url", load_settings().get("olx_chat_url"))
        marker_path(account).write_text(
            json.dumps(marker, ensure_ascii=False), encoding="utf-8"
        )
        LEGACY_MARKER_PATH.unlink()
    save_accounts({"active": account["id"], "accounts": [account]})


def migrate_global_data_to_account() -> None:
    """products.json/conversations.json globale (din versiunile cu date
    comune) devin datele contului activ — acum datele sunt per cont."""
    accounts = load_accounts()
    account = active_account(accounts) or (
        accounts["accounts"][0] if accounts["accounts"] else None
    )
    if account is None:
        return  # datele globale raman pe loc pana apare primul cont
    for name in ("products.json", "conversations.json"):
        src = Path("data") / name
        dst = account_data_dir(account["id"]) / name
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
            logger.info("Date migrate la contul {}: {}", account["id"], name)


def migrate_account_colors() -> None:
    """Fixeaza culorile conturilor create inainte de paleta, ca sa nu se mai
    schimbe la stergerea altui cont."""
    accounts = load_accounts()
    missing = [a for a in accounts["accounts"] if not isinstance(a.get("color"), int)]
    if not missing:
        return
    for position, account in enumerate(accounts["accounts"]):
        account.setdefault("color", position % ACCOUNT_COLORS)
    save_accounts(accounts)


migrate_legacy_profile()
migrate_global_data_to_account()
migrate_account_colors()


# Numar de ordine global pentru erori. Doua conturi care cad in acelasi
# moment (ex. pica reteaua) pot avea acelasi timestamp; fara un contor,
# ordinea la imbinare ar depinde de ordinea conturilor, nu de cand s-a
# intamplat. itertools.count e atomic in CPython.
_error_seq = itertools.count()


class BotRunner:
    """Ruleaza bucla de polling OLX a UNUI cont, intr-un thread propriu.

    Fiecare cont OLX are runner-ul lui (vezi BotFleet): profil de browser
    separat, storage separat, setari separate. Mai multe conturi pot raspunde
    in acelasi timp, fiecare la mesajele lui.
    """

    def __init__(self, account_id: str):
        self.account_id = account_id
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._start_lock = threading.Lock()
        self.last_poll: str | None = None
        # modelul cu care ruleaza botul acum ("groq:llama-3.1-8b-instant") —
        # UI-ul il compara cu setarile salvate ca sa ofere repornirea
        self.active_llm: str | None = None
        self.last_error: str | None = None
        self.errors_today = 0
        self._errors_date = datetime.now(timezone.utc).date()
        self._errors: list[dict] = []
        self._error_lock = threading.RLock()

    def account(self) -> dict | None:
        """Contul, recitit de pe disc — eticheta se poate schimba intre timp."""
        return find_account(load_accounts(), self.account_id)

    def record_error(self, message: str) -> None:
        with self._error_lock:
            self.errors_for_today()  # reseteaza daca s-a schimbat ziua
            self.errors_today += 1
            self.last_error = message
            account = self.account()
            self._errors.append({
                "id": f"err_{uuid.uuid4().hex[:10]}",
                "seq": next(_error_seq),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
                # cu mai multe conturi active, o eroare fara cont nu spune nimic
                "account_id": self.account_id,
                "account_label": (
                    account_display_name(account) if account else self.account_id
                ),
            })
            # Previne cresterea nelimitata intr-un proces care ruleaza mult timp.
            self._errors = self._errors[-100:]

    def errors_for_today(self) -> int:
        with self._error_lock:
            today = datetime.now(timezone.utc).date()
            if today != self._errors_date:
                self._errors_date = today
                self.errors_today = 0
                self.last_error = None
                self._errors.clear()
            return self.errors_today

    def get_errors(self) -> list[dict]:
        with self._error_lock:
            self.errors_for_today()
            return list(reversed(self._errors))

    def clear_errors(self) -> int:
        with self._error_lock:
            cleared = len(self._errors)
            self._errors.clear()
            self.errors_today = 0
            self.last_error = None
            return cleared

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def stopping(self) -> bool:
        """True intre cererea de oprire si terminarea efectiva a thread-ului
        (botul termina ciclul curent si inchide browserul)."""
        return self.running and self._stop_event.is_set()

    def start(self) -> None:
        # lock: doua POST /api/bot/start simultane nu pornesc doua thread-uri
        with self._start_lock:
            if self.running:
                return
            self._stop_event.clear()
            self.last_error = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def stop_and_wait(self, timeout: float = 20) -> None:
        """Opreste botul si asteapta inchiderea browserului — necesar inainte
        de a sterge sau schimba profilul, cat timp Chromium il tine deschis."""
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        try:
            # import local: playwright e necesar doar cand chiar pornesti botul
            from adapters.llm.groq_adapter import GroqAdapter
            from adapters.olx.browser_client import (
                BrowserClient,
                ConversationClosedError,
                LoginRequiredError,
            )

            account = self.account()
            if account is None:
                raise LoginRequiredError("Contul a fost șters între timp.")
            if not account_connected(account):
                raise LoginRequiredError(
                    f"Contul „{account_display_name(account)}” nu e conectat. "
                    "Conectează-l din dashboard."
                )
            settings = load_settings(account)
            # datele (produse, conversatii) sunt strict ale contului activ
            storage = account_storage(account)
            llm = _build_llm(settings)
            backend = (settings.get("llm_backend") or config.LLM_BACKEND).lower()
            self.active_llm = f"{backend}:{getattr(llm, 'model', '?')}"
            handler = MessageHandler(
                llm=llm,
                storage=storage,
                embeddings=config.build_embeddings(),
                seller=settings.get("seller_info"),
            )
            use_queue = config.USE_QUEUE and hasattr(storage, "enqueue_job")
            if config.USE_QUEUE and not use_queue:
                logger.warning(
                    "USE_QUEUE=true dar STORAGE_BACKEND nu e 'db' — "
                    "raman pe procesare inline."
                )
            chat_url = (
                read_marker(account).get("chat_url")
                or settings.get("olx_chat_url")
                or "https://www.olx.ro/myaccount/answers/"
            )
            browser = BrowserClient(
                email=config.OLX_EMAIL,
                password=config.OLX_PASSWORD,
                profile_dir=account["profile_dir"],
                chat_url=chat_url,
            )
            try:
                browser.start()
            except LoginRequiredError as e:
                # sesiunea a expirat / nu exista — invalidam markerul contului
                # ca UI-ul sa arate "neconectat" si sa ceara re-login
                marker_path(account).unlink(missing_ok=True)
                self.record_error(str(e))
                logger.warning(
                    "[{}] Login OLX necesar: {}", account_display_name(account), e
                )
                browser.stop()
                return
        except Exception as e:
            self.record_error(str(e))
            logger.error("[{}] Botul nu a putut porni: {}", self.account_id, e)
            return

        logger.info("Bot pornit pe contul {}.", account_display_name(account))
        try:
            while not self._stop_event.is_set():
                try:
                    self.last_poll = datetime.now(timezone.utc).isoformat()
                    if use_queue:
                        # Producator: mesaj nou -> job in coada.
                        # (Workerii genereaza raspunsurile: `python worker.py`.)
                        for mesaj in browser.get_new_messages():
                            cid = mesaj["olx_conversation_id"]
                            if (
                                not storage.is_processed(cid, mesaj["text"])
                                and not storage.has_active_job(cid)
                            ):
                                storage.enqueue_job(
                                    cid,
                                    mesaj["text"],
                                    buyer_name=mesaj.get("buyer_name"),
                                    ad_title=mesaj.get("ad_title"),
                                )
                        # Expeditor: trimite raspunsurile deja generate de workeri.
                        while (
                            not self._stop_event.is_set()
                            and (job := storage.claim_job_to_send()) is not None
                        ):
                            try:
                                if job["response_text"]:
                                    browser.send_reply(
                                        job["olx_conversation_id"], job["response_text"]
                                    )
                                    storage.mark_conversation_status(
                                        job["olx_conversation_id"],
                                        job["buyer_message"],
                                        "sent",
                                    )
                                storage.mark_job_sent(job["id"])
                            except Exception as e:
                                # jobul nu ramane blocat in 'sending'
                                storage.mark_conversation_status(
                                    job["olx_conversation_id"],
                                    job["buyer_message"],
                                    "failed",
                                )
                                storage.fail_job(job["id"], str(e))
                                raise
                    else:
                        # Procesare inline (comportamentul MVP1, implicit).
                        # try per mesaj: o conversatie cu probleme nu le
                        # blocheaza pe celelalte din acelasi ciclu
                        for mesaj in browser.get_new_messages():
                            if self._stop_event.is_set():
                                break  # oprire ceruta — nu incepem alta conversatie
                            try:
                                raspuns = handler.process(mesaj)
                                if raspuns is not None:
                                    browser.send_reply(mesaj["olx_conversation_id"], raspuns)
                                    storage.mark_conversation_status(
                                        mesaj["olx_conversation_id"],
                                        mesaj["text"],
                                        "sent",
                                    )
                            except ConversationClosedError as e:
                                # cont sters / fir inchis: OLX nu ofera caseta
                                # de raspuns. Nu e o defectiune a botului, deci
                                # nu incarcam centrul de erori — doar marcam.
                                storage.mark_conversation_status(
                                    mesaj["olx_conversation_id"],
                                    mesaj["text"],
                                    "failed",
                                )
                                logger.info(
                                    "[{}] Sar conversatia {} — nu accepta raspunsuri: {}",
                                    account_display_name(account),
                                    mesaj["olx_conversation_id"], e,
                                )
                            except Exception as e:
                                storage.mark_conversation_status(
                                    mesaj["olx_conversation_id"],
                                    mesaj["text"],
                                    "failed",
                                )
                                self.record_error(str(e))
                                logger.error(
                                    "[{}] Eroare la conversatia {}: {}",
                                    account_display_name(account),
                                    mesaj["olx_conversation_id"], e,
                                )
                except Exception as e:
                    self.record_error(str(e))
                    logger.error(
                        "[{}] Eroare in bucla botului: {}",
                        account_display_name(account),
                        e,
                    )
                interval = load_settings(account)["poll_interval_seconds"]
                self._stop_event.wait(timeout=interval)
        finally:
            self.active_llm = None
            browser.stop()
            logger.info("Bot oprit pe contul {}.", account_display_name(account))

    def status(self) -> dict:
        account = self.account()
        return {
            "account_id": self.account_id,
            "account_label": (
                account_display_name(account) if account else self.account_id
            ),
            "running": self.running,
            "stopping": self.stopping,
            "last_poll": self.last_poll,
            "active_llm": self.active_llm if self.running else None,
            "errors_today": self.errors_for_today(),
            "last_error": self.last_error,
        }


class BotFleet:
    """Runner-ele active, cate unul per cont OLX.

    Botul raspunde simultan pe toate conturile pornite; fiecare runner are
    browserul, storage-ul si setarile contului lui, deci conturile nu se
    incurca intre ele.
    """

    def __init__(self):
        self._runners: dict[str, BotRunner] = {}
        self._lock = threading.Lock()

    def get(self, account_id: str) -> BotRunner:
        """Runner-ul contului, creat la prima cerere (nu porneste nimic)."""
        with self._lock:
            runner = self._runners.get(account_id)
            if runner is None:
                runner = self._runners[account_id] = BotRunner(account_id)
            return runner

    def existing(self) -> list[BotRunner]:
        with self._lock:
            return list(self._runners.values())

    def running_ids(self) -> set[str]:
        return {r.account_id for r in self.existing() if r.running}

    @property
    def any_running(self) -> bool:
        return any(r.running for r in self.existing())

    def start_account(self, account_id: str) -> BotRunner:
        runner = self.get(account_id)
        runner.start()
        return runner

    def stop_account(self, account_id: str, wait: bool = False) -> None:
        with self._lock:
            runner = self._runners.get(account_id)
        if runner is None:
            return
        runner.stop_and_wait() if wait else runner.stop()

    def start_connected(self) -> list[str]:
        """Porneste botul pe toate conturile conectate. Intoarce id-urile."""
        started = []
        for account in load_accounts()["accounts"]:
            # contul aflat in login are profilul deschis de fereastra de login;
            # il sarim, dar pornim restul conturilor (altfel un login in curs
            # ar bloca inutil toata flota)
            if login_launcher.running and login_launcher.account_id == account["id"]:
                logger.info(
                    "Sar peste contul {} — are fereastra de login deschisa.",
                    account_display_name(account),
                )
                continue
            if account_connected(account):
                self.start_account(account["id"])
                started.append(account["id"])
        if len(started) > 1 and config.STORAGE_BACKEND == "db":
            # backend-ul db nu are inca o coloana account_id: tabelele sunt
            # comune, deci doua conturi active si-ar amesteca produsele si
            # conversatiile. Pe json datele sunt deja separate pe directoare.
            logger.warning(
                "STORAGE_BACKEND=db nu separa datele pe conturi — cu {} conturi "
                "pornite simultan, produsele si conversatiile se amesteca. "
                "Foloseste STORAGE_BACKEND=json pana se adauga coloana account_id.",
                len(started),
            )
        return started

    def stop_all(self, wait: bool = False) -> list[str]:
        stopped = [r.account_id for r in self.existing() if r.running]
        for runner in self.existing():
            runner.stop_and_wait() if wait else runner.stop()
        return stopped

    def forget(self, account_id: str) -> None:
        """Scoate runner-ul unui cont sters (dupa ce a fost oprit)."""
        with self._lock:
            self._runners.pop(account_id, None)

    def statuses(self) -> list[dict]:
        """Cate o stare per cont din registru, inclusiv conturile nepornite."""
        return [
            self.get(a["id"]).status() | {"connected": account_connected(a)}
            for a in load_accounts()["accounts"]
        ]

    def all_errors(self) -> list[dict]:
        """Erorile tuturor conturilor, cea mai recenta prima.

        Ordonam dupa numarul de ordine, nu dupa timestamp: doua erori din
        aceeasi milisecunda ar da altfel o ordine arbitrara.
        """
        errors = [e for r in self.existing() for e in r.get_errors()]
        return sorted(errors, key=lambda e: e["seq"], reverse=True)

    def clear_errors(self) -> int:
        return sum(r.clear_errors() for r in self.existing())


fleet = BotFleet()

app = FastAPI(title="OLX Bot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dashboard local; de restrans la deploy
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- #
# produse
# --------------------------------------------------------------------- #

@app.get("/api/products")
def list_products(account_id: str | None = None):
    """Produsele conturilor vizate, fiecare marcat cu contul lui.

    Fiecare cont are catalogul lui: acelasi obiect vandut pe doua conturi
    inseamna doua produse distincte (vezi /api/products/{id}/copy).
    """
    products = []
    for account in accounts_in_scope(account_id):
        storage = config.build_storage(account["id"])
        for product in storage.get_products():
            products.append(
                migrate_product(product)
                | {
                    "account_id": account["id"],
                    "account_label": account_display_name(account),
                }
            )
    return products


def _find_product(product_id: str, account_id: str | None) -> tuple[dict, dict]:
    """(produs, cont) — cauta produsul in conturile vizate."""
    for account in accounts_in_scope(account_id):
        storage = config.build_storage(account["id"])
        product = next(
            (p for p in storage.get_products() if p.get("id") == product_id), None
        )
        if product is not None:
            return migrate_product(product), account
    raise HTTPException(status_code=404, detail="Produs inexistent")


@app.get("/api/products/{product_id}")
def get_product(product_id: str, account_id: str | None = None):
    product, account = _find_product(product_id, account_id)
    return product | {
        "account_id": account["id"],
        "account_label": account_display_name(account),
    }


def _target_account(account_id: str | None) -> dict:
    """Contul pe care se scrie. Scrierile au nevoie de o tinta clara: cu mai
    multe conturi, "contul curent" nu mai e evident, asa ca UI-ul trimite
    explicit account_id (cade pe contul selectat doar pentru compatibilitate).
    """
    if account_id in (None, "", "all"):
        account = active_account()
        if account is None:
            raise HTTPException(
                status_code=409, detail="Niciun cont OLX — adaugă un cont întâi"
            )
        return account
    return _account_or_404(account_id)


def _owner_of_product(product_id: str | None) -> dict | None:
    """Contul care detine deja produsul, daca exista undeva."""
    if not product_id:
        return None
    for account in load_accounts()["accounts"]:
        storage = config.build_storage(account["id"])
        if any(p.get("id") == product_id for p in storage.get_products()):
            return account
    return None


@app.post("/api/products")
def save_product(product: dict, account_id: str | None = None):
    # Ordinea conteaza: contul cerut explicit, apoi cel din corpul cererii,
    # apoi PROPRIETARUL actual al produsului. Fara ultimul pas, o editare
    # careia i s-a pierdut account_id pe drum ar salva produsul pe contul
    # selectat in dashboard — adica l-ar muta tacit intre conturi.
    explicit = account_id or product.get("account_id")
    owner = _owner_of_product(product.get("id")) if not explicit else None
    account = owner if owner is not None else _target_account(explicit)
    storage = config.build_storage(account["id"])
    if not product.get("id"):
        product["id"] = f"prod_{uuid.uuid4().hex[:6]}"
    product = empty_product() | migrate_product(product)
    # campurile de cont sunt doar adnotari pentru UI, nu se salveaza in catalog
    saved = storage.save_product(
        {k: v for k, v in product.items() if k not in ("account_id", "account_label")}
    )
    return saved | {
        "account_id": account["id"],
        "account_label": account_display_name(account),
    }


@app.post("/api/products/{product_id}/copy")
def copy_product(product_id: str, body: dict | None = None):
    """Copiaza un produs pe alte conturi.

    Copiile sunt independente dupa creare: le editezi separat pe fiecare cont
    (preturile si stocurile difera in general de la un cont la altul).
    """
    body = body or {}
    product, source = _find_product(product_id, body.get("account_id"))
    targets = body.get("target_account_ids") or []
    if not targets:
        raise HTTPException(status_code=400, detail="Niciun cont țintă selectat")

    copied = []
    for target_id in targets:
        if target_id == source["id"]:
            continue  # copierea pe contul sursa n-ar face decat sa suprascrie
        target = _account_or_404(target_id)
        storage = config.build_storage(target["id"])
        # ID NOU intotdeauna: copiile sunt produse independente. Cu acelasi id
        # pe doua conturi, o editare sau o stergere "pe id" ar putea nimeri
        # produsul altui cont, iar lista pe toate conturile ar avea chei duble.
        clone = dict(product) | {"id": f"prod_{uuid.uuid4().hex[:6]}"}
        storage.save_product(clone)
        copied.append({"account_id": target["id"], "product_id": clone["id"]})
    return {"copied": copied, "count": len(copied)}


@app.delete("/api/products/{product_id}")
def delete_product(product_id: str, account_id: str | None = None):
    _, account = _find_product(product_id, account_id)
    config.build_storage(account["id"]).delete_product(product_id)
    return {"ok": True, "account_id": account["id"]}


# --------------------------------------------------------------------- #
# conversatii + statistici
# --------------------------------------------------------------------- #

@app.get("/api/conversations")
def list_conversations(account_id: str | None = None):
    """Firele de conversatie, grupate dupa conversatia OLX.

    Fiecare fir contine istoricul complet al schimburilor (mesaj cumparator +
    raspuns bot), plus numele interlocutorului si titlul anuntului (culese de
    bot din antetul conversatiei; None pentru intrarile vechi, dinainte sa le
    salvam), plus contul OLX pe care a venit mesajul.

    Implicit aduna conversatiile tuturor conturilor; `?account_id=<id>` le
    filtreaza pe unul singur.
    """
    entries = conversations_in_scope(account_id)
    threads: dict[str, dict] = {}
    for e in sorted(entries, key=lambda c: c.get("timestamp", "")):
        cid = e.get("olx_conversation_id") or e.get("id", "")
        # acelasi id de conversatie poate exista pe doua conturi diferite
        key = f"{e['account_id']}:{cid}"
        thread = threads.setdefault(key, {
            "olx_conversation_id": cid,
            "account_id": e["account_id"],
            "account_label": e["account_label"],
            "buyer_name": None,
            "ad_title": None,
            "product_id": None,
            "last_timestamp": "",
            "messages": [],
        })
        thread["messages"].append({
            "id": e.get("id"),
            "timestamp": e.get("timestamp", ""),
            "buyer_message": e.get("buyer_message", ""),
            "bot_response": e.get("bot_response", ""),
            "status": e.get("status", "sent"),
        })
        thread["last_timestamp"] = e.get("timestamp") or thread["last_timestamp"]
        # cele mai recente valori cunoscute descriu firul
        for key in ("buyer_name", "ad_title", "product_id"):
            if e.get(key):
                thread[key] = e[key]
    return sorted(
        threads.values(), key=lambda t: t["last_timestamp"], reverse=True
    )


@app.get("/api/stats/messages-per-day")
def messages_per_day(account_id: str | None = None):
    conversations = conversations_in_scope(account_id)
    counts = Counter(
        c["timestamp"][:10] for c in conversations if c.get("timestamp")
    )
    today = datetime.now(timezone.utc).date()
    return [
        {"date": str(day), "count": counts.get(str(day), 0)}
        for day in (today - timedelta(days=i) for i in range(6, -1, -1))
    ]


# --------------------------------------------------------------------- #
# bot control
# --------------------------------------------------------------------- #

def _bot_status(account_id: str | None = None) -> dict:
    """Starea botului. Campurile de sus sunt agregate pe toate conturile
    (botul ruleaza pe fiecare separat), iar `accounts` da detaliul per cont."""
    today = datetime.now(timezone.utc).date().isoformat()
    messages_today = sum(
        1 for c in conversations_in_scope(account_id)
        if (c.get("timestamp") or "").startswith(today)
    )
    accounts = fleet.statuses()
    running = [a for a in accounts if a["running"]]
    # cea mai recenta eroare in TIMP, nu ultima in ordinea conturilor
    newest_error = next(iter(fleet.all_errors()), None)
    return {
        "running": bool(running),
        "accounts_running": len(running),
        "accounts_connected": sum(1 for a in accounts if a["connected"]),
        # se opreste = toate cele pornite sunt in curs de oprire
        "stopping": bool(running) and all(a["stopping"] for a in running),
        "last_poll": max((a["last_poll"] for a in running if a["last_poll"]),
                         default=None),
        # modelul cu care ruleaza botul efectiv (None cand e oprit) — UI-ul
        # il compara cu setarile salvate si ofera repornirea la diferente
        "active_llm": running[0]["active_llm"] if running else None,
        "poll_interval_seconds": load_settings()["poll_interval_seconds"],
        "messages_today": messages_today,
        "errors_today": sum(a["errors_today"] for a in accounts),
        "last_error": newest_error["message"] if newest_error else None,
        "last_error_account": newest_error["account_label"] if newest_error else None,
        # starea fiecarui cont: UI-ul are comutator individual per cont
        "accounts": accounts,
    }


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/bot/status")
def bot_status(account_id: str | None = None):
    return _bot_status(account_id)


@app.get("/api/bot/errors")
def bot_errors():
    """Erorile tuturor conturilor, cele mai noi primele (fiecare marcata cu
    contul pe care a aparut)."""
    return fleet.all_errors()


@app.delete("/api/bot/errors")
def clear_bot_errors():
    return {"cleared": fleet.clear_errors()}


def _guard_login_window(account_id: str | None = None) -> None:
    """Fereastra de login tine deschis profilul de browser al unui cont — doua
    procese pe acelasi profil Chromium se blocheaza reciproc. Blocheaza doar
    pornirea contului aflat in login; celelalte conturi pot porni linistite."""
    if not login_launcher.running:
        return
    if account_id is not None and login_launcher.account_id != account_id:
        return
    raise HTTPException(
        status_code=409,
        detail="Fereastra de login e deschisă — finalizează login-ul întâi.",
    )


@app.post("/api/bot/start")
def bot_start():
    """Porneste botul pe TOATE conturile conectate — fiecare raspunde la
    mesajele lui, in acelasi timp. Contul aflat in login e sarit."""
    started = fleet.start_connected()
    time.sleep(0.5)  # lasa thread-urile sa porneasca sau sa cada imediat
    return _bot_status() | {"started": started}


@app.post("/api/bot/stop")
def bot_stop():
    """Opreste botul pe toate conturile."""
    return _bot_status() | {"stopped": fleet.stop_all()}


@app.post("/api/bot/restart")
def bot_restart():
    """Opreste si reporneste botul pe toate conturile conectate — aplica
    setarile noi (modelul LLM)."""
    fleet.stop_all(wait=True)
    started = fleet.start_connected()
    time.sleep(0.5)  # lasa thread-urile sa porneasca sau sa cada imediat
    return _bot_status() | {"started": started}


# --- control per cont: fiecare cont are comutatorul lui in dashboard ------ #

def _account_or_404(account_id: str) -> dict:
    account = find_account(load_accounts(), account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cont inexistent")
    return account


@app.post("/api/bot/accounts/{account_id}/start")
def bot_start_account(account_id: str):
    account = _account_or_404(account_id)
    _guard_login_window(account_id)
    if not account_connected(account):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Contul „{account_display_name(account)}” nu e conectat "
                "— fă login întâi."
            ),
        )
    fleet.start_account(account_id)
    time.sleep(0.5)
    return _bot_status()


@app.post("/api/bot/accounts/{account_id}/stop")
def bot_stop_account(account_id: str):
    _account_or_404(account_id)
    fleet.stop_account(account_id)
    return _bot_status()


@app.post("/api/bot/accounts/{account_id}/restart")
def bot_restart_account(account_id: str):
    _account_or_404(account_id)
    _guard_login_window(account_id)
    fleet.stop_account(account_id, wait=True)
    fleet.start_account(account_id)
    time.sleep(0.5)
    return _bot_status()


# --------------------------------------------------------------------- #
# conectare cont OLX (login manual — CAPTCHA)
# --------------------------------------------------------------------- #

class LoginLauncher:
    """Lanseaza login.py ca proces separat: deschide o fereastra reala de
    browser pe desktopul userului pentru login manual (OLX cere CAPTCHA).

    Rulam ca subprocess pentru ca Playwright sync nu poate rula in bucla
    asyncio a serverului.
    """

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self.account_id: str | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, account: dict) -> None:
        if self.running:
            return
        self.account_id = account["id"]
        self._proc = subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_DIR / "login.py"),
                "--profile",
                account["profile_dir"],
            ],
            cwd=str(PROJECT_DIR),
        )

    def last_result(self) -> str | None:
        """'success' | 'failed' | None (inca ruleaza / n-a rulat)."""
        if self._proc is None or self.running:
            return None
        return "success" if self._proc.returncode == 0 else "failed"


login_launcher = LoginLauncher()


@app.get("/api/olx/session")
def olx_session():
    accounts = load_accounts()
    account = active_account(accounts)

    def info(a: dict) -> dict:
        return account_info(a, accounts) | {"active": a["id"] == accounts.get("active")}

    return {
        "connected": account is not None and account_connected(account),
        "login_running": login_launcher.running,
        "last_result": login_launcher.last_result(),
        "account": info(account) if account else None,
        # sursa unica de adevar pentru selectorul de cont din toate paginile:
        # apar TOATE conturile, inclusiv cele fara date, ca sa le poti selecta
        "accounts": [info(a) for a in accounts["accounts"]],
    }


@app.post("/api/olx/login")
def olx_login():
    """Deschide fereastra de login pentru contul activ (creat daca lipseste)."""
    if login_launcher.running:
        return {"started": False, "reason": "already_running"}
    accounts = load_accounts()
    account = active_account(accounts)
    if account is None:
        account = create_account(accounts)
    # botul tine profilul contului deschis headless — oprim DOAR runner-ul
    # acestui cont (Chromium nu accepta doua procese pe acelasi profil);
    # celelalte conturi continua sa raspunda
    fleet.stop_account(account["id"], wait=True)
    login_launcher.start(account)
    return {"started": True}


@app.post("/api/olx/accounts/{account_id}/login")
def olx_login_account(account_id: str):
    """Deschide fereastra de login pentru UN cont anume.

    Cu mai multe conturi, "logheaza contul activ" nu mai are sens: reconectezi
    exact contul a carui sesiune a expirat, din lista de conturi.
    """
    if login_launcher.running:
        raise HTTPException(
            status_code=409,
            detail="O fereastră de login e deja deschisă — termin-o pe aceea întâi.",
        )
    account = _account_or_404(account_id)
    # botul acestui cont tine profilul deschis headless; Chromium nu accepta
    # doua procese pe acelasi profil, deci il oprim doar pe el
    fleet.stop_account(account_id, wait=True)
    login_launcher.start(account)
    return {"started": True, "account_id": account_id}


@app.post("/api/olx/accounts")
def add_olx_account(body: dict | None = None):
    """Cont nou = profil de browser separat (sesiune izolata de celelalte).
    Devine contul activ si se deschide fereastra de login pentru el."""
    if login_launcher.running:
        raise HTTPException(status_code=409, detail="Un login e deja în curs")
    accounts = load_accounts()
    account = create_account(accounts, (body or {}).get("label"))
    # contul nou devine cel selectat in dashboard (lentila de vizualizare
    # pentru produse/setari) — nu opreste botii celorlalte conturi
    if accounts.get("active") != account["id"]:
        accounts["active"] = account["id"]
        save_accounts(accounts)
    login_launcher.start(account)
    return {"id": account["id"], "label": account["label"]}


@app.post("/api/olx/accounts/{account_id}/activate")
def activate_olx_account(account_id: str):
    """Schimba contul selectat in dashboard — cel ale carui produse si setari
    le editezi. NU opreste niciun bot: conturile ruleaza independent, fiecare
    cu comutatorul lui."""
    accounts = load_accounts()
    account = find_account(accounts, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cont inexistent")
    accounts["active"] = account_id
    save_accounts(accounts)
    return {"active": account_id, "bot_stopped": False}


@app.delete("/api/olx/accounts/{account_id}")
def sign_out_olx_account(account_id: str, purge: bool = False):
    """Deconectare: sterge DOAR sesiunea (profilul de browser); contul ramane
    in lista ca "neconectat", iar produsele/conversatiile/setarile lui raman
    salvate si il regasesc la re-login.

    Cu ?purge=true sterge definitiv tot: sesiune + date + contul din lista.
    """
    if login_launcher.running:
        raise HTTPException(
            status_code=409,
            detail="Un login e în curs — reîncearcă după ce se închide fereastra.",
        )
    accounts = load_accounts()
    account = find_account(accounts, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cont inexistent")
    # botul acestui cont tine profilul deschis — nu putem sterge peste el
    fleet.stop_account(account_id, wait=True)
    # profilul contine si markerul de login => contul apare "neconectat"
    shutil.rmtree(account["profile_dir"], ignore_errors=True)
    if not purge:
        return {"ok": True, "active": accounts.get("active"), "purged": False}

    fleet.forget(account_id)
    shutil.rmtree(account_data_dir(account_id), ignore_errors=True)
    accounts["accounts"] = [a for a in accounts["accounts"] if a["id"] != account_id]
    if accounts.get("active") == account_id:
        accounts["active"] = (
            accounts["accounts"][0]["id"] if accounts["accounts"] else None
        )
    save_accounts(accounts)
    return {"ok": True, "active": accounts.get("active"), "purged": True}


# --------------------------------------------------------------------- #
# setari
# --------------------------------------------------------------------- #

# --------------------------------------------------------------------- #
# modele LLM — Ollama local (live) + Groq online (live, cu fallback)
# --------------------------------------------------------------------- #

# lista de rezerva cand API-ul Groq nu e accesibil (cheie lipsa/offline)
GROQ_FALLBACK_MODELS = [
    {"name": "llama-3.1-8b-instant", "note": "rapid"},
    {"name": "llama-3.3-70b-versatile", "note": "calitate"},
]
# modelele Groq care nu sunt LLM-uri de chat (nu au sens in dropdown)
_GROQ_EXCLUDE = ("whisper", "tts", "guard", "embedding", "moderation", "orpheus")

# cache scurt ca dashboard-ul sa nu bata API-urile la fiecare afisare
_models_cache: dict = {"at": 0.0, "data": None}
MODELS_CACHE_TTL = 60  # secunde


def _list_ollama_models() -> dict:
    """Modelele descarcate local, citite live de la Ollama (/api/tags)."""
    import requests

    try:
        resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=2)
        resp.raise_for_status()
        models = [
            {
                "name": m["name"],
                "size_gb": round(m.get("size", 0) / 1e9, 1),
            }
            for m in resp.json().get("models", [])
        ]
        return {"available": True, "models": models, "host": config.OLLAMA_HOST}
    except Exception as e:
        logger.debug("Ollama indisponibil: {}", e)
        return {"available": False, "models": [], "host": config.OLLAMA_HOST}


def _list_groq_models() -> dict:
    """Modelele de chat Groq, live din API; fallback pe lista hardcodata."""
    import os

    import requests

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        # fara cheie nu are sens sa oferim modele online — UI-ul arata
        # hint de configurare (ca la Ollama cand nu ruleaza)
        return {"available": False, "models": []}
    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        names = sorted(
            m["id"]
            for m in resp.json().get("data", [])
            if m.get("active", True)
            and not any(x in m["id"].lower() for x in _GROQ_EXCLUDE)
        )
        return {"available": True, "models": [{"name": n} for n in names]}
    except Exception as e:
        logger.debug("API-ul Groq nu a putut fi citit ({}) — lista de rezerva.", e)
        return {"available": True, "models": GROQ_FALLBACK_MODELS}


@app.get("/api/llm/models")
def get_llm_models(refresh: bool = False):
    """Modelele selectabile: locale (Ollama, live) + online (Groq)."""
    now = time.time()
    if (
        not refresh
        and _models_cache["data"] is not None
        and now - _models_cache["at"] < MODELS_CACHE_TTL
    ):
        return _models_cache["data"]
    data = {"ollama": _list_ollama_models(), "groq": _list_groq_models()}
    _models_cache.update(at=now, data=data)
    return data


# --------------------------------------------------------------------- #
# descarcare modele Ollama (pull cu progres)
# --------------------------------------------------------------------- #

# progresul pull-urilor pornite din dashboard: model -> stare
_pull_jobs: dict[str, dict] = {}
_pull_lock = threading.Lock()


def _run_ollama_pull(model: str) -> None:
    """Ruleaza `ollama pull` prin API-ul HTTP, cu progres streaming."""
    import requests

    job = _pull_jobs[model]
    try:
        with requests.post(
            f"{config.OLLAMA_HOST}/api/pull",
            json={"model": model, "stream": True},
            stream=True,
            timeout=(5, 3600),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                update = json.loads(line)
                if update.get("error"):
                    raise RuntimeError(update["error"])
                status = update.get("status", "")
                total = update.get("total") or 0
                completed = update.get("completed") or 0
                with _pull_lock:
                    job["status"] = status
                    if total:
                        job["percent"] = round(completed * 100 / total, 1)
        with _pull_lock:
            job.update(done=True, status="success", percent=100.0)
        _models_cache["data"] = None  # modelul nou sa apara imediat in lista
        logger.info("Model Ollama descarcat: {}", model)
    except Exception as e:
        with _pull_lock:
            job.update(done=True, error=str(e), status="failed")
        logger.error("Descarcarea modelului {} a esuat: {}", model, e)


@app.post("/api/ollama/pull")
def start_ollama_pull(body: dict):
    """Porneste descarcarea unui model Ollama in fundal."""
    model = str(body.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Numele modelului lipseste.")
    if not _list_ollama_models()["available"]:
        raise HTTPException(
            status_code=503,
            detail="Ollama nu ruleaza. Instaleaza-l de pe ollama.com si porneste-l.",
        )
    with _pull_lock:
        job = _pull_jobs.get(model)
        if job and not job.get("done"):
            return {"started": False, "already_running": True}
        _pull_jobs[model] = {
            "status": "starting", "percent": 0.0, "done": False, "error": None,
        }
    threading.Thread(target=_run_ollama_pull, args=(model,), daemon=True).start()
    return {"started": True}


@app.get("/api/ollama/pull/status")
def get_ollama_pull_status():
    """Progresul descarcarilor pornite din dashboard."""
    with _pull_lock:
        return {model: dict(job) for model, job in _pull_jobs.items()}


@app.get("/api/settings")
def get_settings(account_id: str | None = None):
    """Setarile conturilor vizate.

    Pe un singur cont, valorile lui. Pe mai multe, valoarea comuna acolo unde
    conturile sunt de acord, iar campurile unde difera sunt listate in `mixed`
    — UI-ul le arata ca "valori diferite" in loc sa aleaga tacit una si sa o
    suprascrie pe cealalta la prima salvare.
    """
    accounts = accounts_in_scope(account_id)
    if not accounts:
        return dict(DEFAULT_SETTINGS) | {"mixed": []}

    per_account = [load_settings(a) for a in accounts]
    # valorile afisate vin de la contul selectat cand e in scope: pe "toate
    # conturile", campurile din `mixed` sunt oricum marcate ca diferite, iar
    # restul sunt identice — deci alegerea conteaza doar pentru cele mixte
    selected = active_account()
    base = next(
        (
            load_settings(a)
            for a in accounts
            if selected is not None and a["id"] == selected["id"]
        ),
        per_account[0],
    )
    values = dict(base)
    mixed = sorted(
        key
        for key in DEFAULT_SETTINGS
        if len({json.dumps(s.get(key), sort_keys=True) for s in per_account}) > 1
    )
    return values | {"mixed": mixed}


@app.put("/api/settings")
def put_settings(settings: dict, account_id: str | None = None):
    """Scrie setarile pe conturile vizate.

    Se scriu DOAR cheile prezente in corpul cererii: in modul "toate
    conturile", campurile pe care nu le-ai atins raman diferite de la un cont
    la altul (fiecare cont isi pastreaza, de exemplu, modelul LLM propriu).
    """
    changes = {k: v for k, v in settings.items() if k in DEFAULT_SETTINGS}
    # scrierea pe toate conturile se cere explicit (account_id="all"); fara
    # parametru scriem doar pe contul selectat, ca o cerere veche sa nu
    # imprastie din greseala setarile peste toate conturile
    accounts = (
        accounts_in_scope("all") if account_id == "all" else [_target_account(account_id)]
    )
    if not accounts:
        raise HTTPException(
            status_code=409, detail="Niciun cont OLX — adaugă un cont întâi"
        )

    previous_level = load_settings(accounts[0]).get("log_level")
    for account in accounts:
        current = load_settings(account)
        current.update(changes)
        save_settings(current, account)

    # nivelul de log e al procesului, nu al contului — il aplicam o data
    new_level = changes.get("log_level")
    if new_level is not None and new_level != previous_level:
        _apply_log_level(new_level)
        logger.info("Nivel log schimbat la {}.", new_level)
    return get_settings(account_id)


if __name__ == "__main__":
    import uvicorn

    _apply_log_level(load_settings().get("log_level", config.LOG_LEVEL))
    uvicorn.run(app, host="127.0.0.1", port=8000)
