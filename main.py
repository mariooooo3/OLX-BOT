import json
import sys
from pathlib import Path
from time import sleep

from loguru import logger

import config
from adapters.olx.browser_client import BrowserClient, LoginRequiredError
from core.message_handler import MessageHandler


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)
    logger.add("logs/bot.log", level=config.LOG_LEVEL,
               rotation="10 MB", retention="14 days", encoding="utf-8")


def _chat_url(account_id: str | None) -> str:
    """olx_chat_url din setarile contului (data/accounts/<id>/settings.json),
    cu fallback pe cele globale (data/settings.json)."""
    paths = []
    if account_id:
        paths.append(Path("data/accounts") / account_id / "settings.json")
    paths.append(Path("data/settings.json"))
    for settings_path in paths:
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if data.get("olx_chat_url"):
                return data["olx_chat_url"]
    return "https://www.olx.ro/myaccount/answers/"


def _active_account() -> tuple[str | None, str, dict]:
    """(account_id, profile_dir, marker) pentru contul activ din
    data/accounts.json.

    Acelasi registru de conturi ca dashboard-ul, ca `python main.py` sa
    porneasca pe contul selectat acolo, nu pe profilul vechi unic.
    """
    accounts_path = Path("data/accounts.json")
    if accounts_path.exists():
        data = json.loads(accounts_path.read_text(encoding="utf-8"))
        account = next(
            (a for a in data.get("accounts", []) if a["id"] == data.get("active")),
            None,
        )
        if account:
            marker = {}
            marker_path = Path(account["profile_dir"]) / "olx_session.json"
            if marker_path.exists():
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            return account["id"], account["profile_dir"], marker
    return None, "data/browser_profile", {}


def main() -> None:
    setup_logging()
    logger.info("Pornesc botul OLX (polling la {} sec).", config.POLL_INTERVAL_SECONDS)

    account_id, profile_dir, marker = _active_account()
    # datele (produse, conversatii) sunt izolate per cont OLX
    storage = config.build_storage(account_id)
    handler = MessageHandler(
        llm=config.build_llm(),
        storage=storage,
        embeddings=config.build_embeddings(),
    )
    browser = BrowserClient(
        email=config.OLX_EMAIL,
        password=config.OLX_PASSWORD,
        profile_dir=profile_dir,
        chat_url=marker.get("chat_url") or _chat_url(account_id),
    )

    try:
        try:
            browser.start()
        except LoginRequiredError as e:
            logger.error("{}", e)
            logger.error("Ruleaza mai intai `python login.py` si logheaza-te o data.")
            return
        while True:
            try:
                mesaje_noi = browser.get_new_messages()
                logger.info("{} mesaje noi.", len(mesaje_noi))
                for mesaj in mesaje_noi:
                    try:
                        raspuns = handler.process(mesaj)
                        if raspuns is not None:
                            browser.send_reply(mesaj["olx_conversation_id"], raspuns)
                            storage.mark_conversation_status(
                                mesaj["olx_conversation_id"], mesaj["text"], "sent"
                            )
                    except Exception:
                        storage.mark_conversation_status(
                            mesaj["olx_conversation_id"], mesaj["text"], "failed"
                        )
                        raise
            except Exception as e:
                logger.error("Eroare in bucla principala: {}", e)
            sleep(config.POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Oprire ceruta de utilizator.")
    finally:
        browser.stop()


if __name__ == "__main__":
    main()
