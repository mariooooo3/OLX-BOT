"""Verificarea sesiunii OLX — logica comuna pentru login.py si bot.

Doua mecanisme, in ordinea asta:

  1. API (principal): OLX tine un cookie `access_token`; cu el ca Bearer,
     GET /api/v1/users/me raspunde 200 + datele contului (nume, email).
     Nu navigheaza pagina, deci se poate apela oricat de des.
  2. DOM (fallback): navigare la /myaccount/ — utilizatorii nelogati sunt
     redirectionati la login; cei logati raman si au elemente de user
     (link MyOLX / logout). Folosit doar daca API-ul se schimba vreodata.
"""
from loguru import logger

BASE_URL = "https://www.olx.ro"
ACCOUNT_URL = f"{BASE_URL}/myaccount/"
ME_API = f"{BASE_URL}/api/v1/users/me/"

# orice element din formularul de login => sigur NU suntem logati
LOGIN_FORM = (
    "input[name='password'], input[name='username'], "
    "[data-testid='login-submit-button']"
)
# element vizibil DOAR pentru utilizatori logati => confirmare pozitiva
LOGGED_IN_MARKER = (
    "[data-testid='myolx-link'], [data-testid='user-avatar'], "
    "a[href*='logout'], a[href*='myaccount']"
)
COOKIE_ACCEPT = "#onetrust-accept-btn-handler"


def _access_token(context) -> str | None:
    try:
        for cookie in context.cookies(BASE_URL):
            if cookie["name"] == "access_token":
                return cookie["value"]
    except Exception:
        pass
    return None


def fetch_me(context) -> dict | None:
    """Datele contului logat ({name, email, ...}) sau None daca nu e logat.

    Nu navigheaza — sigur de apelat in timp ce userul scrie in pagina.
    """
    token = _access_token(context)
    if not token:
        return None
    try:
        resp = context.request.get(
            ME_API,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=15000,
        )
        if not resp.ok:
            return None
        data = resp.json().get("data") or {}
        return data if data.get("id") else None
    except Exception as e:
        logger.debug("users/me a esuat: {}", e)
        return None


def accept_cookies(page) -> None:
    try:
        page.click(COOKIE_ACCEPT, timeout=3000)
    except Exception:
        pass  # bannerul nu e mereu prezent


def dom_logged_in(page) -> bool:
    """Fallback: navigheaza la /myaccount/ si cauta semne de user logat.

    Navigheaza! A se apela doar cand formularul de login nu e pe ecran.
    """
    try:
        page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
        accept_cookies(page)
        try:
            page.wait_for_selector(
                f"{LOGIN_FORM}, {LOGGED_IN_MARKER}", timeout=12000
            )
        except Exception:
            pass
        url = page.url.lower()
        if "login" in url or "/auth" in url:
            return False
        if page.query_selector(LOGIN_FORM):
            return False
        return page.query_selector(LOGGED_IN_MARKER) is not None
    except Exception as e:
        logger.debug("Verificarea DOM a sesiunii a esuat: {}", e)
        return False


def login_form_on_screen(page) -> bool:
    """Verificare pasiva (fara navigare) — nu deranjeaza userul care scrie."""
    try:
        url = page.url.lower()
        if "login" in url or "/auth" in url:
            return True
        return page.query_selector(LOGIN_FORM) is not None
    except Exception:
        return True
