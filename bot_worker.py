"""Bucla de polling a UNUI cont OLX, ca proces de sine statator — menit sa
ruleze intr-un container Docker separat, cate unul per cont.

De ce exista pe langa server.py (care are deja BotFleet cu un thread per
cont): un thread nu poate avea propriul IP de iesire fara sa complice tot
procesul, dar un container poate — fiecare container isi are propriul
proxy/VPN (vezi core/accounts.py -> account_proxy), deci conturi multiple
pe aceeasi masina nu mai ies pe acelasi IP (motivul intreg al acestui
fisier). Dashboard-ul (server.py + UI) ramane neschimbat, pe Windows,
pentru ca nu face trafic catre OLX — doar bucla asta il face.

Storage-ul ramane JSON, pe folderul contului (data/accounts/<id>/), montat
ca volum de pe host in container — vezi Dockerfile.worker si
docker-compose.example.yml. Acelasi folder e citit si de server.py, deci
dashboard-ul vede automat conversatiile/erorile unui cont care ruleaza
intr-un container, fara nicio sincronizare suplimentara.

Pornire (local, fara Docker, utila la testare):
    ACCOUNT_ID=acc_xxxxxx python bot_worker.py

Pornire in container:  vezi docker-compose.example.yml
"""
import os
import signal
import sys
import time
from datetime import datetime, timezone

from loguru import logger

import config
from adapters.olx.browser_client import BrowserClient, ConversationClosedError, LoginRequiredError
from core.accounts import (
    account_connected,
    account_display_name,
    account_profile_dir,
    account_proxy,
    find_account,
    load_accounts,
    load_settings,
    write_bot_heartbeat,
)
from core.message_handler import MessageHandler

# cat asteapta inainte sa reincerce cand contul nu e conectat / login expirat —
# nu iesim imediat cu eroare (ar porni un restart-loop rapid in Docker), dar
# nici nu batem la interval de polling normal cand oricum nu are ce face
RETRY_WAIT_SECONDS = 30


def setup_logging() -> None:
    """Doar stderr — intr-un container, `docker logs` citeste stdout/stderr;
    un fisier separat pe container ar fi izolat si greu de gasit."""
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)


class _Stopping:
    """Flag setat de SIGTERM/SIGINT (docker stop) — bucla se opreste dupa
    ciclul curent, nu la mijlocul trimiterii unui raspuns."""

    def __init__(self) -> None:
        self.requested = False

    def handle(self, signum, frame) -> None:  # noqa: ARG002
        logger.info("Semnal de oprire primit ({}) — opresc dupa ciclul curent.", signum)
        self.requested = True


def _resolve_account(account_id: str) -> dict:
    account = find_account(load_accounts(), account_id)
    if account is None:
        raise SystemExit(
            f"Contul {account_id!r} nu exista in data/accounts.json. "
            "Verifica ACCOUNT_ID si volumul montat cu datele contului."
        )
    return account


def main() -> None:
    setup_logging()
    account_id = os.environ.get("ACCOUNT_ID", "").strip()
    if not account_id:
        raise SystemExit(
            "Variabila de mediu ACCOUNT_ID lipseste — cine ruleaza containerul "
            "asta? Seteaz-o la id-ul contului din data/accounts.json "
            "(ex. ACCOUNT_ID=acc_429ab3)."
        )

    stopping = _Stopping()
    signal.signal(signal.SIGTERM, stopping.handle)
    signal.signal(signal.SIGINT, stopping.handle)

    account = _resolve_account(account_id)
    label = account_display_name(account)
    logger.info("Worker pornit pentru contul {} ({}).", label, account_id)

    errors_today = 0
    errors_date = datetime.now(timezone.utc).date()
    last_error: str | None = None

    def heartbeat(running: bool | None = None, **extra) -> None:
        write_bot_heartbeat(
            account_id,
            running=(not stopping.requested) if running is None else running,
            errors_today=errors_today,
            last_error=last_error,
            **extra,
        )

    browser: BrowserClient | None = None
    try:
        while not stopping.requested:
            account = _resolve_account(account_id)  # eticheta/proxy pot fi editate din dashboard
            if not account_connected(account):
                logger.warning(
                    "Contul {} nu e conectat — astept re-login din dashboard "
                    "({}s).", label, RETRY_WAIT_SECONDS,
                )
                heartbeat(running=False, last_poll=None, active_llm=None)
                time.sleep(RETRY_WAIT_SECONDS)
                continue

            settings = load_settings(account)
            storage = config.build_storage(account_id)
            llm = config.build_llm(settings)
            backend = (settings.get("llm_backend") or config.LLM_BACKEND).lower()
            active_llm = f"{backend}:{getattr(llm, 'model', '?')}"
            handler = MessageHandler(
                llm=llm,
                storage=storage,
                embeddings=config.build_embeddings(),
                seller=settings.get("seller_info"),
            )
            chat_url = settings.get("olx_chat_url") or "https://www.olx.ro/myaccount/answers/"
            browser = BrowserClient(
                profile_dir=account_profile_dir(account),
                chat_url=chat_url,
                proxy=account_proxy(account),
            )
            try:
                browser.start()
            except LoginRequiredError as e:
                last_error = str(e)
                logger.warning("[{}] {} — astept re-login ({}s).", label, e, RETRY_WAIT_SECONDS)
                heartbeat(running=False, last_poll=None, active_llm=None)
                browser.stop()
                browser = None
                time.sleep(RETRY_WAIT_SECONDS)
                continue

            logger.info("[{}] Sesiune OLX valida — incep polling-ul.", label)
            # reconectare reusita dupa o eroare anterioara (ex. sesiune expirata
            # temporar) — heartbeat-ul nu mai are voie sa arate eroarea veche,
            # altfel dashboard-ul pare sa raporteze o problema care nu mai exista
            last_error = None
            heartbeat(last_poll=None, active_llm=active_llm)

            try:
                while not stopping.requested:
                    if errors_date != datetime.now(timezone.utc).date():
                        errors_date = datetime.now(timezone.utc).date()
                        errors_today = 0
                        last_error = None
                    try:
                        for mesaj in browser.get_new_messages():
                            if stopping.requested:
                                break  # oprire ceruta — nu incepem alta conversatie
                            try:
                                raspuns = handler.process(mesaj)
                                if raspuns is not None:
                                    browser.send_reply(mesaj["olx_conversation_id"], raspuns)
                                    storage.mark_conversation_status(
                                        mesaj["olx_conversation_id"], mesaj["text"], "sent",
                                    )
                            except ConversationClosedError as e:
                                # cont sters / fir inchis — nu e o defectiune a
                                # botului, doar marcam si mergem mai departe
                                storage.mark_conversation_status(
                                    mesaj["olx_conversation_id"], mesaj["text"], "failed",
                                )
                                logger.info(
                                    "[{}] Sar conversatia {} — nu accepta raspunsuri: {}",
                                    label, mesaj["olx_conversation_id"], e,
                                )
                            except Exception as e:
                                storage.mark_conversation_status(
                                    mesaj["olx_conversation_id"], mesaj["text"], "failed",
                                )
                                errors_today += 1
                                last_error = str(e)
                                logger.error(
                                    "[{}] Eroare la conversatia {}: {}",
                                    label, mesaj["olx_conversation_id"], e,
                                )
                    except Exception as e:
                        errors_today += 1
                        last_error = str(e)
                        logger.error("[{}] Eroare in bucla botului: {}", label, e)

                    heartbeat(
                        last_poll=datetime.now(timezone.utc).isoformat(),
                        active_llm=active_llm,
                    )
                    if stopping.requested:
                        break
                    interval = load_settings(account)["poll_interval_seconds"]
                    for _ in range(int(interval)):
                        if stopping.requested:
                            break
                        time.sleep(1)
            finally:
                browser.stop()
                browser = None
    finally:
        heartbeat(running=False, active_llm=None)
        if browser is not None:
            browser.stop()
        logger.info("[{}] Worker oprit.", label)


if __name__ == "__main__":
    main()
