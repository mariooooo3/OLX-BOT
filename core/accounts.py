"""Registrul de conturi OLX + setarile lor — folosit de server.py (dashboard).

Extras din server.py ca sa nu existe doua copii ale aceleiasi logici: un
cont, o sesiune, un profil de browser, niste setari, un proxy de iesire.
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

    Rezolvat din registrul central (data/proxies.json, vezi core/proxies.py)
    prin `account["proxy_id"]` — un singur loc de adevar, ca acelasi proxy sa
    nu ajunga din greseala pe doua conturi. Conturile inca nemigrate (fara
    `proxy_id`, cu proxy-ul inca inline din versiunile vechi) cad pe campul
    vechi — nu ar trebui sa se intample in practica, migrate_legacy_proxies()
    ruleaza o data la pornirea serverului, dar e o plasa de siguranta ca un
    cont sa nu ramana brusc fara proxy daca migrarea a fost sarita cumva.
    """
    # import local: evita ciclul (core.proxies importa din acest modul, la
    # randul lui, pentru account_display_name/load_accounts)
    from core.proxies import find_proxy, list_proxies, resolve_connection

    proxy_id = account.get("proxy_id")
    if proxy_id:
        proxy = find_proxy(list_proxies(), proxy_id)
        if proxy is not None:
            return resolve_connection(proxy)
        logger.warning(
            "Contul {} referă un proxy inexistent ({}) — iese fără proxy.",
            account.get("id"), proxy_id,
        )
        return None
    legacy = account.get("proxy")
    return legacy if isinstance(legacy, dict) and legacy.get("server") else None


def migrate_legacy_proxies() -> None:
    """Muta proxy-urile vechi (dict inline pe `account["proxy"]`) in
    registrul central data/proxies.json — vezi core/proxies.py pentru motiv.
    Idempotenta si sigura de rulat la fiecare pornire a serverului: un cont
    deja migrat (are `proxy_id`) trece neschimbat."""
    from core.proxies import create_proxy

    accounts = load_accounts()
    changed = False
    for account in accounts["accounts"]:
        if account.get("proxy_id"):
            if "proxy" in account:  # curatare: campul vechi ar fi trebuit sters deja
                account.pop("proxy", None)
                changed = True
            continue
        legacy = account.get("proxy")
        if not isinstance(legacy, dict) or not legacy.get("server"):
            continue
        proxy = create_proxy(
            label=f"Proxy {account_display_name(account)}",
            server=legacy.get("server", ""),
            username=legacy.get("username"),
            password=legacy.get("password"),
        )
        account["proxy_id"] = proxy["id"]
        account.pop("proxy", None)
        changed = True
        logger.info("Proxy migrat in registru pentru contul {}: {}", account["id"], proxy["id"])
    if changed:
        save_accounts(accounts)


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
        # .as_posix(): mereu cu '/', portabil intre Windows si Linux —
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
