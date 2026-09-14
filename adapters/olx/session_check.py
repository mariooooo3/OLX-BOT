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
# element vizibil DOAR pentru utilizatori logati => confirmare pozitiva.
# DOAR data-testid-uri specifice componentei de user logat — NU selectori
# largi de tipul a[href*='myaccount'] sau a[href*='logout']: verificat
# practic (test de sarcina cu 9 proxy-uri concurente), un link generic din
# navigare care contine "myaccount" in href poate exista si pe pagina
# NElogata, inainte ca redirectul catre login.olx.ro sa se termine — un
# selector asa de larg da fals-pozitiv "logat" exact cand pagina e prinsa
# la mijloc de tranzitie (mult mai probabil sub proxy lent/incarcat).
LOGGED_IN_MARKER = "[data-testid='myolx-link'], [data-testid='user-avatar']"
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

    Fail-closed: daca pagina nu apuca sa afiseze NICI formularul de login,
    NICI un marker de user logat in timpul alocat (proxy lent/incarcat —
    verificat practic la 9 conturi concurente), consideram "neconfirmat" =>
    False, nu True. O pagina prinsa la mijloc de tranzitie (inainte ca
    redirectul catre login.olx.ro sa se termine) nu e o dovada de login.

    wait_until="networkidle", nu doar "domcontentloaded": shell-ul initial al
    paginii /myaccount/ contine elementele de user (data-testid myolx-link /
    user-avatar) INAINTE ca JS-ul sa determine ca nu esti logat si sa
    redirectioneze catre login.olx.ro — verificat practic (9 proxy-uri
    concurente: cele lente au prins exact acest interval si au raportat fals
    "logat"). "networkidle" da timp cererii de verificare a autentificarii
    sa se termine si redirectul sa apuce sa se produca inainte sa citim DOM-ul.
    """
    try:
        page.goto(ACCOUNT_URL, wait_until="networkidle", timeout=20000)
        accept_cookies(page)
        try:
            page.wait_for_selector(
                f"{LOGIN_FORM}, {LOGGED_IN_MARKER}", timeout=12000
            )
        except Exception:
            logger.debug(
                "Nici formularul de login, nici un marker de user logat nu "
                "au aparut la timp — consider sesiunea neconfirmata."
            )
            return False
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
