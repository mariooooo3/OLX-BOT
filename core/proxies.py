"""Registrul central de proxy-uri — un singur loc de adevar pentru adresele
folosite de conturile OLX, plus validarea lor (test de conectivitate reala).

De ce un registru separat si nu doar campul `proxy` de pe fiecare cont (cum
era inainte): cu proxy-ul scris direct pe cont, e usor sa copiezi din
greseala aceeasi adresa pe doua conturi — exact ce README-ul avertizeaza sa
NU faci ("un cont OLX = un proxy fix"). Cu un registru, fiecare proxy exista
o singura data (`data/proxies.json`) si un cont il REFERA prin `proxy_id`;
UI-ul poate arata clar "acest proxy e deja folosit de contul X" inainte sa
permita dubla alocare, in loc sa afli abia dupa ce ambele conturi par
corelate de OLX.

Conturile vechi, cu proxy-ul inca inline (dict pe `account["proxy"]"`), sunt
migrate automat in registru la pornirea serverului — vezi
core/accounts.py -> migrate_legacy_proxies().
"""
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from loguru import logger

PROXIES_PATH = Path("data/proxies.json")
_WRITE_LOCK = threading.Lock()

# Cerem chiar OLX, nu un endpoint generic de "ce IP am" — un proxy poate fi
# functional in general dar blocat punctual pentru domeniul OLX (IP-uri de
# datacenter, liste negre etc.), ceea ce un test generic nu ar prinde.
TEST_URL = "https://www.olx.ro/"
DEFAULT_TIMEOUT = 8.0

# Geolocarea IP-ului, interogata PRIN acelasi proxy — confirma nu doar ca
# proxy-ul functioneaza, ci si ca iese din tara la care te astepti. Bot-ul
# declara mereu locale="ro-RO"/timezone="Europe/Bucharest" (vezi
# adapters/olx/browser_client.py); un proxy care iese din alta tara e el
# insusi o discrepanta suspecta pentru un cont OLX.ro, indiferent cat de
# bine functioneaza tehnic (verificat practic: a dus la invalidarea unei
# sesiuni reale in timpul testarii acestei functionalitati).
#
# Endpoint-ul de trace al Cloudflare (nu un API de geo-IP dedicat) —
# disponibil pe orice IP Cloudflare, fara limite practice de rata si fara
# nevoie de cheie API. Un API de geo-IP dedicat (ex. ipapi.co) s-a dovedit
# nefiabil in practica: prin proxy-uri partajate intens (folosite de multi
# utilizatori simultan), limita lui de rate se atinge aproape instant.
GEO_LOOKUP_URL = "https://1.1.1.1/cdn-cgi/trace"
GEO_LOOKUP_TIMEOUT = 5.0
EXPECTED_COUNTRY = "RO"


# --------------------------------------------------------------------- #
# stocare
# --------------------------------------------------------------------- #

def load_proxies() -> dict:
    if PROXIES_PATH.exists():
        try:
            return json.loads(PROXIES_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("data/proxies.json corupt — pornesc de la un registru gol.")
            return {"proxies": []}
    return {"proxies": []}


def save_proxies(data: dict) -> None:
    PROXIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROXIES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PROXIES_PATH)


def list_proxies() -> list[dict]:
    return load_proxies()["proxies"]


def find_proxy(proxies: list[dict], proxy_id: str | None) -> dict | None:
    return next((p for p in proxies if p["id"] == proxy_id), None)


def create_proxy(
    label: str, server: str, username: str | None = None, password: str | None = None
) -> dict:
    with _WRITE_LOCK:
        data = load_proxies()
        proxy = {
            "id": f"proxy_{uuid.uuid4().hex[:8]}",
            "label": (label or "").strip() or server,
            "server": server.strip(),
            "username": (username or "").strip() or None,
            "password": (password or "").strip() or None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_check": None,
            # verificarea rapida (test_proxy) si cea completa (test_proxy_full,
            # cu Chromium real) se pastreaza separat — un proxy poate trece
            # una si pica pe cealalta, vezi test_proxy_full()
            "last_full_check": None,
        }
        data["proxies"].append(proxy)
        save_proxies(data)
        logger.info("Proxy adaugat in registru: {} ({})", proxy["id"], proxy["label"])
        return proxy


def update_proxy(proxy_id: str, **fields) -> dict | None:
    """Actualizeaza campurile date. `username`/`password` goale sunt
    ignorate (raman neschimbate) — acelasi tipar ca la editarea proxy-ului
    unui cont: nu poti sterge parola scriind peste ea un camp gol din
    greseala, doar explicit (nu exista inca un buton dedicat pentru asta,
    dar comportamentul e simetric cu restul aplicatiei)."""
    with _WRITE_LOCK:
        data = load_proxies()
        proxy = find_proxy(data["proxies"], proxy_id)
        if proxy is None:
            return None
        if "label" in fields and fields["label"] is not None:
            proxy["label"] = str(fields["label"]).strip() or proxy["label"]
        if "server" in fields and fields["server"] is not None:
            server = str(fields["server"]).strip()
            if server:
                proxy["server"] = server
        if fields.get("username"):
            proxy["username"] = str(fields["username"]).strip()
        if fields.get("password"):
            proxy["password"] = str(fields["password"]).strip()
        save_proxies(data)
        return proxy


def set_last_check(proxy_id: str, result: dict) -> dict | None:
    with _WRITE_LOCK:
        data = load_proxies()
        proxy = find_proxy(data["proxies"], proxy_id)
        if proxy is None:
            return None
        proxy["last_check"] = {
            "ok": result["ok"],
            "error": result.get("error"),
            "latency_ms": result.get("latency_ms"),
            "country": result.get("country"),
            "country_mismatch": result.get("country_mismatch", False),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        save_proxies(data)
        return proxy


def set_last_full_check(proxy_id: str, result: dict) -> dict | None:
    """La fel ca set_last_check, dar pentru rezultatul verificarii complete
    (test_proxy_full) — pastrata separat, ca un proxy sa nu para "verificat
    complet" doar pentru ca a trecut testul rapid ulterior."""
    with _WRITE_LOCK:
        data = load_proxies()
        proxy = find_proxy(data["proxies"], proxy_id)
        if proxy is None:
            return None
        proxy["last_full_check"] = {
            "ok": result["ok"],
            "error": result.get("error"),
            "latency_ms": result.get("latency_ms"),
            "country": result.get("country"),
            "country_mismatch": result.get("country_mismatch", False),
            "browser_ok": result.get("browser_ok"),
            "browser_error": result.get("browser_error"),
            "browser_latency_ms": result.get("browser_latency_ms"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        save_proxies(data)
        return proxy


def delete_proxy(proxy_id: str) -> bool:
    with _WRITE_LOCK:
        data = load_proxies()
        before = len(data["proxies"])
        data["proxies"] = [p for p in data["proxies"] if p["id"] != proxy_id]
        if len(data["proxies"]) == before:
            return False
        save_proxies(data)
        logger.info("Proxy sters din registru: {}", proxy_id)
        return True


# --------------------------------------------------------------------- #
# rezolvare pentru BrowserClient (Playwright) + reprezentare pentru UI
# --------------------------------------------------------------------- #

def resolve_connection(proxy: dict | None) -> dict | None:
    """Forma asteptata de BrowserClient/login.py: {"server", "username"?,
    "password"?} — fara campurile de registru (id, label, last_check)."""
    if not proxy or not proxy.get("server"):
        return None
    conn = {"server": proxy["server"]}
    if proxy.get("username"):
        conn["username"] = proxy["username"]
    if proxy.get("password"):
        conn["password"] = proxy["password"]
    return conn


def public_proxy(proxy: dict, assigned_account: dict | None) -> dict:
    """Reprezentarea proxy-ului pentru dashboard — fara parola in clar
    (doar `has_password`), plus contul care il foloseste acum (daca vreunul)."""
    # import local: evita ciclul (core.accounts importa functii din acest
    # modul in account_proxy() / migrate_legacy_proxies())
    from core.accounts import account_display_name

    return {
        "id": proxy["id"],
        "label": proxy.get("label") or proxy["server"],
        "server": proxy["server"],
        "username": proxy.get("username"),
        "has_password": bool(proxy.get("password")),
        "created_at": proxy.get("created_at"),
        "last_check": proxy.get("last_check"),
        "last_full_check": proxy.get("last_full_check"),
        "account_id": assigned_account["id"] if assigned_account else None,
        "account_label": account_display_name(assigned_account) if assigned_account else None,
    }


def assigned_account(proxy_id: str, accounts: dict | None = None) -> dict | None:
    """Contul care foloseste acest proxy acum, sau None daca niciunul."""
    from core.accounts import load_accounts

    accounts = accounts if accounts is not None else load_accounts()
    return next((a for a in accounts["accounts"] if a.get("proxy_id") == proxy_id), None)


# --------------------------------------------------------------------- #
# validare — test de conectivitate reala prin proxy, catre OLX
# --------------------------------------------------------------------- #

def _proxy_url(server: str, username: str | None, password: str | None) -> str:
    """URL-ul complet (cu credentiale, daca exista) in formatul asteptat de
    `requests` — user/parola pot contine caractere speciale, deci trebuie
    encodate procentual inainte sa intre in URL."""
    if not username and not password:
        return server
    parsed = urlsplit(server)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = quote(username or "", safe="")
    if password:
        auth += f":{quote(password, safe='')}"
    return f"{scheme}://{auth}@{host}{port}"


def _clean_error(exc: Exception, fallback: str) -> str:
    """Mesajele exceptiilor din `requests` pot fi lungi si tehnice (URL-uri
    complete, stack-uri de librarii) — pastram doar un mesaj scurt, util."""
    text = str(exc)
    if "Missing dependencies for SOCKS support" in text:
        return (
            "Suport SOCKS5 lipsă pe server — instalează pachetul 'pysocks' "
            "(pip install pysocks) și repornește dashboard-ul."
        )
    return fallback


def _result(
    ok: bool, error: str | None = None, latency_ms: float | None = None,
    country: str | None = None,
) -> dict:
    return {
        "ok": ok,
        "error": error,
        "latency_ms": latency_ms,
        "country": country,
        # None cand geo-lookup-ul n-a mers (nu blocam testul pentru asta) —
        # doar True/False cand chiar stim tara si o putem compara
        "country_mismatch": (country is not None and country != EXPECTED_COUNTRY),
    }


def _lookup_country(proxy_url: str, timeout: float) -> str | None:
    """Codul de tara (ISO, ex. "RO", "GB") al IP-ului de iesire al proxy-ului,
    interogat PRIN el — sau None daca lookup-ul esueaza (best-effort: nu
    trebuie sa strice rezultatul principal al testului doar pentru ca
    lookup-ul de geolocare e indisponibil).

    Raspunsul e text simplu (nu JSON), cate o pereche cheie=valoare pe
    linie; ne intereseaza doar "loc=<COD_TARA>".
    """
    try:
        response = requests.get(
            GEO_LOOKUP_URL,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
        )
        response.raise_for_status()
        for line in response.text.splitlines():
            if line.startswith("loc="):
                code = line.split("=", 1)[1].strip().upper()
                return code or None
        return None
    except Exception as e:
        logger.debug("Geolocare proxy esuata (nu blocheaza testul): {}", e)
        return None


def test_proxy(
    server: str, username: str | None = None, password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Testeaza daca acest proxy poate ajunge efectiv la OLX, plus (best-effort)
    tara din care iese IP-ul.

    Returneaza {"ok", "error", "latency_ms", "country", "country_mismatch"}.
    `country_mismatch` e doar informativ — un proxy dintr-o alta tara tot
    functioneaza tehnic (ok=True), dar UI-ul arata un avertisment clar
    inainte sa-l asignezi pe un cont, in loc sa afli abia dupa ce sesiunea
    contului a fost invalidata (vezi comentariul la GEO_LOOKUP_URL).

    Nu arunca exceptii — orice eroare de retea devine un rezultat "ok": False
    cu mesaj explicativ, ca apelantul (endpoint API) sa-l poata arata direct
    in UI fara try/except suplimentar.
    """
    server = (server or "").strip()
    if not server:
        return _result(False, "Adresa proxy lipsește.")
    if "://" not in server:
        return _result(
            False,
            "Adresa trebuie să includă protocolul (ex. socks5://host:port sau http://host:port).",
        )

    try:
        proxy_url = _proxy_url(server, username, password)
    except Exception as e:
        return _result(False, f"Adresa proxy nu e validă: {e}")

    started = time.monotonic()
    try:
        # stream=True + close() imediat: nu descarcam pagina intreaga, doar
        # confirmam ca proxy-ul duce la un raspuns HTTP valid de la OLX
        response = requests.get(
            TEST_URL,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        response.close()
        if response.status_code >= 500:
            return _result(
                False, f"OLX a răspuns cu eroare {response.status_code} prin acest proxy.",
                latency_ms,
            )
        country = _lookup_country(proxy_url, GEO_LOOKUP_TIMEOUT)
        return _result(True, None, latency_ms, country)
    except requests.exceptions.ProxyError as e:
        return _result(
            False, _clean_error(e, "Proxy-ul a refuzat conexiunea sau autentificarea a eșuat."),
        )
    except requests.exceptions.ConnectTimeout:
        return _result(False, "Timeout la conectarea prin proxy.")
    except requests.exceptions.SSLError as e:
        return _result(False, _clean_error(e, "Eroare SSL prin acest proxy."))
    except requests.exceptions.RequestException as e:
        return _result(False, _clean_error(e, "Nu am putut ajunge la OLX prin acest proxy."))
    except Exception as e:
        return _result(False, str(e) or "Eroare necunoscută la testarea proxy-ului.")


def test_proxy_full(
    server: str, username: str | None = None, password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Verificare completa: mai intai testul rapid (retea + geo, de mai sus),
    apoi — doar daca acela trece — o verificare cu Chromium REAL (vezi
    adapters/olx/browser_client.py:browser_check_proxy()).

    De ce in doi pasi si nu direct cu browserul: un proxy poate trece testul
    rapid (facut cu `requests`) si totusi sa se comporte diferit sub stiva
    TLS/HTTP a unui browser real — verificat practic, a fost exact cauza
    pentru care o sesiune OLX reala a fost invalidata desi testul rapid
    raportase proxy-ul functional. Testul complet e mult mai lent (lanseaza
    Chromium de la zero, ~5-15s), de-asta ramane un buton separat ("Testeaza
    complet"), nu validarea implicita la fiecare salvare.

    Returneaza campurile lui test_proxy() plus "browser_ok", "browser_error",
    "browser_latency_ms" (toate None daca testul rapid a picat deja — n-are
    rost sa lansam un browser cand reteaua de baza nu functioneaza).
    """
    result = dict(
        test_proxy(server, username, password, timeout),
        browser_ok=None, browser_error=None, browser_latency_ms=None,
    )
    if not result["ok"]:
        return result

    # import local: Playwright e o dependinta grea (lanseaza Chromium),
    # necesara doar pentru testul complet — celelalte functii din acest
    # modul (registrul, testul rapid) raman utilizabile fara ea
    from adapters.olx.browser_client import browser_check_proxy

    browser_result = browser_check_proxy(server, username, password)
    result["browser_ok"] = browser_result["ok"]
    result["browser_error"] = browser_result["error"]
    result["browser_latency_ms"] = browser_result["latency_ms"]
    if not browser_result["ok"]:
        result["ok"] = False
        result["error"] = (
            "Testul rapid a trecut, dar browserul real nu a putut folosi "
            f"acest proxy: {browser_result['error']}"
        )
    return result
