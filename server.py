"""API server pentru dashboard-ul web (ui/).

Expune peste botul existent:
  - CRUD produse        -> data/products.json (prin JSONAdapter)
  - conversatii         -> data/conversations.json
  - start/stop bot      -> bucla de polling ruleaza intr-un thread separat
  - setari              -> data/settings.json

Pornire:  uvicorn server:app --port 8000
"""
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
    "groq_model": "llama-3.1-8b-instant",
    "log_level": config.LOG_LEVEL,
    "olx_chat_url": "https://www.olx.ro/myaccount/answers/",
}

def _build_llm(settings: dict):
    """Construieste LLM-ul respectand modelul din setari (pentru Groq)."""
    if config.LLM_BACKEND == "ollama":
        from adapters.llm.ollama_adapter import OllamaAdapter
        return OllamaAdapter()
    from adapters.llm.groq_adapter import GroqAdapter
    return GroqAdapter(model=settings["groq_model"])


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


def _storage_or_409():
    storage = account_storage()
    if storage is None:
        raise HTTPException(
            status_code=409, detail="Niciun cont OLX — adaugă un cont întâi"
        )
    return storage


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


def create_account(accounts: dict, label: str | None = None) -> dict:
    account_id = f"acc_{uuid.uuid4().hex[:6]}"
    label = (label or "").strip() or f"Cont {len(accounts['accounts']) + 1}"
    profile_dir = PROFILES_ROOT / account_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    account = {"id": account_id, "label": label, "profile_dir": str(profile_dir)}
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


migrate_legacy_profile()
migrate_global_data_to_account()


class BotRunner:
    """Ruleaza bucla de polling OLX intr-un thread, controlata din API."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._start_lock = threading.Lock()
        self.last_poll: str | None = None
        self.last_error: str | None = None
        self.errors_today = 0
        self._errors_date = datetime.now(timezone.utc).date()
        self._errors: list[dict] = []
        self._error_lock = threading.RLock()

    def record_error(self, message: str) -> None:
        with self._error_lock:
            self.errors_for_today()  # reseteaza daca s-a schimbat ziua
            self.errors_today += 1
            self.last_error = message
            self._errors.append({
                "id": f"err_{uuid.uuid4().hex[:10]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
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
            from adapters.olx.browser_client import BrowserClient, LoginRequiredError

            account = active_account()
            if account is None or not account_connected(account):
                raise LoginRequiredError(
                    "Niciun cont OLX conectat. Conectează un cont din dashboard."
                )
            settings = load_settings(account)
            # datele (produse, conversatii) sunt strict ale contului activ
            storage = account_storage(account)
            llm = _build_llm(settings)
            handler = MessageHandler(llm=llm, storage=storage)
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
                logger.warning("Login OLX necesar: {}", e)
                browser.stop()
                return
        except Exception as e:
            self.record_error(str(e))
            logger.error("Botul nu a putut porni: {}", e)
            return

        logger.info("Bot pornit din dashboard.")
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
                            except Exception as e:
                                storage.mark_conversation_status(
                                    mesaj["olx_conversation_id"],
                                    mesaj["text"],
                                    "failed",
                                )
                                self.record_error(str(e))
                                logger.error(
                                    "Eroare la conversatia {}: {}",
                                    mesaj["olx_conversation_id"], e,
                                )
                except Exception as e:
                    self.record_error(str(e))
                    logger.error("Eroare in bucla botului: {}", e)
                interval = load_settings(account)["poll_interval_seconds"]
                self._stop_event.wait(timeout=interval)
        finally:
            browser.stop()
            logger.info("Bot oprit.")


runner = BotRunner()

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
def list_products():
    storage = account_storage()
    return storage.get_products() if storage else []


@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    storage = account_storage()
    products = storage.get_products() if storage else []
    product = next((p for p in products if p.get("id") == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="Produs inexistent")
    return product


@app.post("/api/products")
def save_product(product: dict):
    storage = _storage_or_409()
    if not product.get("id"):
        product["id"] = f"prod_{uuid.uuid4().hex[:6]}"
    return storage.save_product(product)


@app.delete("/api/products/{product_id}")
def delete_product(product_id: str):
    storage = _storage_or_409()
    storage.delete_product(product_id)
    return {"ok": True}


# --------------------------------------------------------------------- #
# conversatii + statistici
# --------------------------------------------------------------------- #

@app.get("/api/conversations")
def list_conversations():
    """Firele de conversatie, grupate dupa conversatia OLX.

    Fiecare fir contine istoricul complet al schimburilor (mesaj cumparator +
    raspuns bot), plus numele interlocutorului si titlul anuntului (culese de
    bot din antetul conversatiei; None pentru intrarile vechi, dinainte sa le
    salvam).
    """
    storage = account_storage()
    entries = storage.get_conversations() if storage else []
    threads: dict[str, dict] = {}
    for e in sorted(entries, key=lambda c: c.get("timestamp", "")):
        cid = e.get("olx_conversation_id") or e.get("id", "")
        thread = threads.setdefault(cid, {
            "olx_conversation_id": cid,
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
def messages_per_day():
    storage = account_storage()
    conversations = storage.get_conversations() if storage else []
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

def _bot_status() -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    storage = account_storage()
    conversations = storage.get_conversations() if storage else []
    messages_today = sum(
        1 for c in conversations
        if (c.get("timestamp") or "").startswith(today)
    )
    return {
        "running": runner.running,
        "stopping": runner.stopping,
        "last_poll": runner.last_poll,
        "poll_interval_seconds": load_settings()["poll_interval_seconds"],
        "messages_today": messages_today,
        "errors_today": runner.errors_for_today(),
        "last_error": runner.last_error,
    }


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/bot/status")
def bot_status():
    return _bot_status()


@app.get("/api/bot/errors")
def bot_errors():
    return runner.get_errors()


@app.delete("/api/bot/errors")
def clear_bot_errors():
    return {"cleared": runner.clear_errors()}


@app.post("/api/bot/start")
def bot_start():
    # fereastra de login tine deschis acelasi profil de browser pe care l-ar
    # folosi botul — doua procese pe un profil Chromium se blocheaza reciproc
    if login_launcher.running:
        raise HTTPException(
            status_code=409,
            detail="Fereastra de login e deschisă — finalizează login-ul întâi.",
        )
    runner.start()
    time.sleep(0.5)  # lasa thread-ul sa porneasca sau sa cada imediat
    return _bot_status()


@app.post("/api/bot/stop")
def bot_stop():
    runner.stop()
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

    def account_info(a: dict) -> dict:
        marker = read_marker(a)
        return {
            "id": a["id"],
            "label": a["label"],
            # emailul + numele contului OLX, salvate de login.py (users/me)
            "username": marker.get("username"),
            "name": marker.get("name"),
            "connected": account_connected(a),
            "active": a["id"] == accounts.get("active"),
        }

    return {
        "connected": account is not None and account_connected(account),
        "login_running": login_launcher.running,
        "last_result": login_launcher.last_result(),
        "account": account_info(account) if account else None,
        "accounts": [account_info(a) for a in accounts["accounts"]],
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
    # botul tine profilul contului deschis headless — il oprim inainte ca
    # login.py sa deschida acelasi profil (Chromium nu accepta doua procese)
    if runner.running:
        runner.stop_and_wait()
    login_launcher.start(account)
    return {"started": True}


@app.post("/api/olx/accounts")
def add_olx_account(body: dict | None = None):
    """Cont nou = profil de browser separat (sesiune izolata de celelalte).
    Devine contul activ si se deschide fereastra de login pentru el."""
    if login_launcher.running:
        raise HTTPException(status_code=409, detail="Un login e deja în curs")
    accounts = load_accounts()
    account = create_account(accounts, (body or {}).get("label"))
    if accounts.get("active") != account["id"]:
        if runner.running:
            runner.stop_and_wait()
        accounts["active"] = account["id"]
        save_accounts(accounts)
    login_launcher.start(account)
    return {"id": account["id"], "label": account["label"]}


@app.post("/api/olx/accounts/{account_id}/activate")
def activate_olx_account(account_id: str):
    """Schimba contul activ. Botul e oprit ca sa nu mai citeasca mesajele
    contului vechi; se reporneste manual pe contul nou."""
    accounts = load_accounts()
    account = find_account(accounts, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cont inexistent")
    bot_stopped = False
    if accounts.get("active") != account_id:
        if runner.running:
            runner.stop_and_wait()
            bot_stopped = True
        accounts["active"] = account_id
        save_accounts(accounts)
    return {"active": account_id, "bot_stopped": bot_stopped}


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
    if accounts.get("active") == account_id and runner.running:
        runner.stop_and_wait()
    # profilul contine si markerul de login => contul apare "neconectat"
    shutil.rmtree(account["profile_dir"], ignore_errors=True)
    if not purge:
        return {"ok": True, "active": accounts.get("active"), "purged": False}

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

@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.put("/api/settings")
def put_settings(settings: dict):
    current = load_settings()
    current.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    save_settings(current)
    return current


if __name__ == "__main__":
    import uvicorn

    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)
    logger.add("logs/bot.log", level=config.LOG_LEVEL,
               rotation="10 MB", retention="14 days", encoding="utf-8")
    uvicorn.run(app, host="127.0.0.1", port=8000)
