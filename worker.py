"""Worker de coada — MVP2.

Proces separat de server: ia joburi din coada (mesaje noi enqueue-uite de
producator), genereaza raspunsul prin core/ (matcher -> prompt -> LLM ->
validare) si il marcheaza 'done'. Serverul (care are browserul) trimite
apoi raspunsurile pe OLX.

Pentru scalare rulezi mai multi workeri simultan — fiecare ia joburi
diferite (claim atomic). Nu are nevoie de browser.

Pornire:  python worker.py
Necesita: STORAGE_BACKEND=db si USE_QUEUE=true in .env.
"""
import sys
import time

from loguru import logger

import config
from core.message_handler import MessageHandler
from core.product_matcher import match_product

IDLE_SLEEP = 2  # secunde intre verificari cand coada e goala


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)

    storage = config.build_storage()
    if not hasattr(storage, "claim_next_job"):
        logger.error(
            "Workerul are nevoie de coada de joburi. Seteaza STORAGE_BACKEND=db "
            "(si USE_QUEUE=true) in .env."
        )
        return

    llm = config.build_llm()
    handler = MessageHandler(
        llm=llm, storage=storage, embeddings=config.build_embeddings()
    )
    logger.info("Worker pornit ({} / {}). Astept joburi...",
                config.LLM_BACKEND, config.STORAGE_BACKEND)

    try:
        while True:
            job = storage.claim_next_job()
            if job is None:
                time.sleep(IDLE_SLEEP)
                continue

            logger.info("Preiau jobul {} (conv {}).",
                        job["id"], job["olx_conversation_id"])
            try:
                product = match_product(
                    job["buyer_message"],
                    storage.get_products(),
                    ad_title=job.get("ad_title"),
                )
                message = {
                    "id": job["id"],
                    "text": job["buyer_message"],
                    "olx_conversation_id": job["olx_conversation_id"],
                    "buyer_name": job.get("buyer_name"),
                    "ad_title": job.get("ad_title"),
                }
                response = handler.process(message)
                # response None = conversatie deja procesata -> nimic de trimis
                storage.complete_job(
                    job["id"], response or "", product["id"] if product else None
                )
                logger.info("Job {} rezolvat.", job["id"])
            except Exception as e:
                logger.error("Job {} esuat: {}", job["id"], e)
                storage.fail_job(job["id"], str(e))
    except KeyboardInterrupt:
        logger.info("Worker oprit.")


if __name__ == "__main__":
    main()
