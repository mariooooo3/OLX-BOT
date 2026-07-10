"""Login manual OLX — o singura data.

OLX protejeaza login-ul cu un CAPTCHA anti-bot (slider). Login-ul automat
nu e posibil, deci deschidem o fereastra reala de browser, te loghezi tu,
iar sesiunea se salveaza intr-un profil persistent pe care botul il
refoloseste ulterior headless.

Rulare:  python login.py [--profile data/browser_profiles/acc_x]

Fiecare cont OLX are propriul profil de browser (--profile), deci sesiunile
mai multor conturi nu se amesteca intre ele.

Pasi:
  1. Se deschide o fereastra Chrome.
  2. Te loghezi cu contul tau OLX (rezolvi si sliderul CAPTCHA).
  3. Scriptul confirma login-ul prin API-ul OLX (users/me), salveaza numele
     si emailul contului + pagina de mesaje, apoi inchide fereastra.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from playwright.sync_api import sync_playwright

from adapters.olx.browser_client import install_playwright_browsers
from adapters.olx.session_check import (
    ACCOUNT_URL,
    dom_logged_in,
    fetch_me,
    login_form_on_screen,
)

load_dotenv(override=True)

sys.stdout.reconfigure(encoding="utf-8")

SETTINGS_PATH = Path("data/settings.json")
# marker scris DOAR dupa un login confirmat — sursa de adevar pentru UI;
# sta in interiorul profilului, deci e per cont
MARKER_NAME = "olx_session.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Login manual OLX")
    parser.add_argument(
        "--profile",
        default="data/browser_profile",
        help="directorul profilului de browser al contului (unul per cont OLX)",
    )
    return parser.parse_args()


def wait_for_login(context, page, timeout_s: int = 600) -> dict | None:
    """Asteapta login-ul manual. Returneaza datele contului (sau {} daca
    doar fallback-ul DOM a confirmat), None daca userul nu s-a logat.

    Verificarea principala e prin API (fara navigare, la 2s), deci nu
    stergem ce scrie userul in formular. Fallback-ul DOM navigheaza, dar
    ruleaza rar si doar cand formularul de login nu e pe ecran.
    """
    deadline = time.time() + timeout_s
    last_dom_check = time.time()
    while time.time() < deadline:
        time.sleep(2)
        try:
            if page.is_closed():
                return None
            me = fetch_me(context)
            if me:
                return me
            if login_form_on_screen(page):
                continue
            # formularul a disparut dar API-ul inca nu confirma — o data la
            # 30s incercam si fallback-ul DOM (navigheaza la /myaccount/)
            if time.time() - last_dom_check > 30:
                last_dom_check = time.time()
                if dom_logged_in(page):
                    return fetch_me(context) or {}
        except Exception:
            return None  # fereastra inchisa de user
    return None


def discover_chat_url(page) -> str | None:
    """Cauta in header link-ul catre chat dupa ce esti logat.

    OLX afiseaza butonul "Chat" ca <a data-testid='header-chat-button'>
    cu href /myaccount/answers/ (vechiul /mesaje/ intoarce 404).
    """
    page.goto("https://www.olx.ro/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    hrefs: list[str] = []
    chat_button = page.query_selector("a[data-testid='header-chat-button'][href]")
    if chat_button:
        hrefs.append(chat_button.get_attribute("href") or "")
    hrefs.extend(
        link.get_attribute("href") or ""
        for link in page.query_selector_all("a[href]")
    )

    patterns = ("/myaccount/answers", "mesaje", "wiadomosci", "/chat")
    for href in hrefs:
        if any(p in href.lower() for p in patterns):
            if href.startswith("/"):
                href = "https://www.olx.ro" + href
            return href.split("?")[0]
    return None


def save_chat_url(url: str) -> None:
    data = {}
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    data["olx_chat_url"] = url
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    profile_dir = Path(args.profile)
    marker_path = profile_dir / MARKER_NAME
    profile_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Deschid fereastra de browser pentru login manual...")

    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=str(profile_dir),
            headless=False,
            locale="ro-RO",
            viewport={"width": 1366, "height": 850},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            # Chrome real pare mai putin ca un bot
            context = p.chromium.launch_persistent_context(
                channel="chrome", **launch_kwargs
            )
        except Exception:
            logger.warning(
                "Chrome nu e instalat — folosesc Chromium-ul Playwright."
            )
            try:
                context = p.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as e:
                if "Executable doesn't exist" not in str(e):
                    raise
                logger.warning("Browserele Playwright lipsesc — le descarc...")
                install_playwright_browsers()
                context = p.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()

        me = fetch_me(context)
        if me:
            logger.info("Esti deja logat din sesiuni anterioare.")
        else:
            page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
            print("\n" + "=" * 64)
            print("  LOGHEAZA-TE IN FEREASTRA DESCHISA")
            print("  - completeaza email + parola")
            print("  - rezolva sliderul CAPTCHA daca apare")
            print("  Fereastra se inchide singura dupa cateva secunde")
            print("  de la login — scriptul detecteaza automat contul.")
            print("=" * 64 + "\n")

            logger.info("Astept sa te loghezi (max 10 minute)...")
            me = wait_for_login(context, page)
            if me is None:
                logger.error(
                    "Login neconfirmat (fereastra inchisa sau timp expirat). "
                    "Reincearca din dashboard."
                )
                try:
                    context.close()
                except Exception:
                    pass
                sys.exit(2)

        # marcam login-ul confirmat (sursa de adevar pentru dashboard)
        marker = {"logged_in_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if me.get("email"):
            marker["username"] = me["email"]
        if me.get("name"):
            marker["name"] = me["name"]
        marker_path.write_text(
            json.dumps(marker, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "Login confirmat: {} ({})",
            me.get("name") or "?",
            me.get("email") or "email nedetectat",
        )

        chat_url = discover_chat_url(page)
        if chat_url:
            marker["chat_url"] = chat_url
            marker_path.write_text(
                json.dumps(marker, ensure_ascii=False), encoding="utf-8"
            )
            save_chat_url(chat_url)
            logger.info("Pagina de mesaje: {} (salvata)", chat_url)
        else:
            logger.warning(
                "Nu am gasit automat link-ul de mesaje. Botul va folosi "
                "valoarea implicita; poti seta manual 'olx_chat_url' in "
                "data/settings.json."
            )

        logger.info("Sesiune salvata in {}. Poti inchide.", profile_dir)
        context.close()

    print("\nGata. Acum poti porni botul din dashboard sau cu `python main.py`.")


if __name__ == "__main__":
    main()
