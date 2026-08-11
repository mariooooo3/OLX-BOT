import sys
from pathlib import Path
from time import sleep

from loguru import logger

import config
from adapters.olx.browser_client import BrowserClient, LoginRequiredError
from core.accounts import (
    account_profile_dir,
    account_proxy,
    active_account,
    load_settings,
    read_marker,
)
from core.message_handler import MessageHandler


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)
    logger.add("logs/bot.log", level=config.LOG_LEVEL,
               rotation="10 MB", retention="14 days", encoding="utf-8")


def main() -> None:
    setup_logging()
    account = active_account()
    account_id = account["id"] if account else None
    settings = load_settings(account)
    poll_interval = int(
        settings.get("poll_interval_seconds") or config.POLL_INTERVAL_SECONDS
    )
    logger.info("Pornesc botul OLX (polling la {} sec).", poll_interval)

    # datele (produse, conversatii) sunt izolate per cont OLX
    storage = config.build_storage(account_id)
    handler = MessageHandler(
        llm=config.build_llm(settings),
        storage=storage,
        embeddings=config.build_embeddings(),
        # locatie/livrare/plata — fara asta botul nu putea raspunde la
        # intrebari de vanzator cand niciun produs nu se potrivea (bug:
        # main.py era singura cale de pornire care omitea seller_info,
        # spre deosebire de BotRunner din server.py si de bot_worker.py)
        seller=settings.get("seller_info"),
    )
    marker = read_marker(account) if account else {}
    browser = BrowserClient(
        email=config.OLX_EMAIL,
        password=config.OLX_PASSWORD,
        profile_dir=account_profile_dir(account) if account else "data/browser_profile",
        chat_url=marker.get("chat_url")
        or settings.get("olx_chat_url")
        or "https://www.olx.ro/myaccount/answers/",
        # fara asta, `python main.py` iesea mereu pe IP-ul masinii chiar
        # daca ai configurat un proxy pentru cont din dashboard — celelalte
        # doua cai de pornire (server.py, bot_worker.py) il foloseau deja
        proxy=account_proxy(account) if account else None,
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
            # recitit la fiecare ciclu — schimbarea din dashboard se aplica
            # din mers, la fel ca in server.py
            poll_interval = int(
                load_settings(account).get("poll_interval_seconds")
                or config.POLL_INTERVAL_SECONDS
            )
            sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Oprire ceruta de utilizator.")
    finally:
        browser.stop()


if __name__ == "__main__":
    main()
