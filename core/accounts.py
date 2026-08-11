"""Registrul de conturi OLX + setarile lor — folosit de server.py (dashboard)
SI de bot_worker.py (procesul de bot per cont, care poate rula intr-un
container Docker separat).

Extras din server.py ca sa nu existe doua copii ale aceleiasi logici: un
cont, o sesiune, un profil de browser, niste setari — indiferent daca botul
lui ruleaza ca thread in acelasi proces cu dashboard-ul (implicit) sau ca
proces separat, eventual containerizat, cu propriul proxy de iesire.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

import config
from core.seller_info import DEFAULT_SELLER_INFO

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
# starea scrisa de un proces de bot EXTERN (container) — vezi
# write_bot_heartbeat / read_bot_heartbeat mai jos
BOT_STATUS_NAME = "bot_status.json"

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


# --------------------------------------------------------------------- #
# setari (globale + suprascrieri per cont)
# --------------------------------------------------------------------- #

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


def account_profile_dir(account: dict) -> str:
    """Calea profilului contului, normalizata cu '/'.

    accounts.json creat pe Windows salveaza calea cu '\\' (str(Path) pe
    Windows) — dar pathlib pe Linux NU trateaza '\\' ca separator, deci un
    container (bot_worker.py) ar cauta un singur folder cu numele literal
    "data\\browser_profiles\\acc_x" in loc de trei foldere imbricate.
    Normalizam mereu la citire (nu doar la scriere in create_account), ca
    si conturile create inainte de acest fix sa functioneze in container
    fara o migrare separata.
    """
    return str(account["profile_dir"]).replace("\\", "/")


def marker_path(account: dict) -> Path:
    return Path(account_profile_dir(account)) / SESSION_MARKER_NAME


def account_data_dir(account_id: str) -> Path:
    return ACCOUNTS_DATA_ROOT / account_id


def account_settings_path(account_id: str) -> Path:
    return account_data_dir(account_id) / "settings.json"


def account_proxy(account: dict) -> dict | None:
    """Proxy-ul de iesire al contului, sau None daca n-are.

    Conturi multiple din acelasi browser/masina ies pe acelasi IP — usor de
    corelat de sistemele anti-frauda OLX. Fiecare cont poate avea propriul
    proxy/VPN (vezi adapters/olx/browser_client.py si server.py — endpoint
    PUT /api/olx/accounts/{id}/proxy).
    """
    proxy = account.get("proxy")
    return proxy if isinstance(proxy, dict) and proxy.get("server") else None


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


def account_display_name(account: dict) -> str:
    """Cum se numeste contul in dashboard: numele/emailul OLX detectat la
    login, altfel eticheta locala ("Cont 2"). Cu mai multe conturi active,
    "Cont 2" nu spune nimic — numele real da."""
    marker = read_marker(account)
    return marker.get("name") or marker.get("username") or account["label"]


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


def create_account(accounts: dict, label: str | None = None) -> dict:
    account_id = f"acc_{uuid.uuid4().hex[:6]}"
    label = (label or "").strip() or f"Cont {len(accounts['accounts']) + 1}"
    profile_dir = PROFILES_ROOT / account_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    account = {
        "id": account_id,
        "label": label,
        # .as_posix(): mereu cu '/', portabil intre Windows (dashboard,
        # login.py) si Linux (container Docker, vezi bot_worker.py) —
        # vezi si account_profile_dir()
        "profile_dir": profile_dir.as_posix(),
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
        "profile_dir": LEGACY_PROFILE_DIR.as_posix(),
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


# --------------------------------------------------------------------- #
# stare externa a botului (container Docker per cont)
#
# Un cont poate rula fie ca thread in procesul dashboard-ului (implicit),
# fie ca proces separat (eventual container) pornit manual cu
# `docker compose up <account_id>` — vezi bot_worker.py. In al doilea caz,
# dashboard-ul nu porneste/opreste nimic (control manual), dar tot trebuie
# sa arate starea: procesul extern scrie periodic un heartbeat pe disc, pe
# care dashboard-ul il citeste cand niciun thread local nu ruleaza pentru
# contul respectiv.
# --------------------------------------------------------------------- #

def bot_status_path(account_id: str) -> Path:
    return account_data_dir(account_id) / BOT_STATUS_NAME


def write_bot_heartbeat(account_id: str, **fields) -> None:
    """Apelata de bot_worker.py la fiecare ciclu de polling, si o data la
    oprire (running=False), ca dashboard-ul sa reflecte starea imediat in
    loc sa astepte expirarea heartbeat-ului."""
    path = bot_status_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"updated_at": datetime.now(timezone.utc).isoformat(), **fields}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_bot_heartbeat(account_id: str, max_age_seconds: float = 180) -> dict | None:
    """Starea scrisa de procesul extern, doar daca e recenta.

    O stare veche inseamna ca procesul a murit fara sa apuce sa scrie
    running=False (container omorat brusc, host repornit) — mai bine o
    ignoram decat sa aratam in dashboard un bot "pornit" care de fapt nu mai
    exista.
    """
    path = bot_status_path(account_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(data["updated_at"])
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age > max_age_seconds:
            return None
        return data
    except Exception:
        return None
