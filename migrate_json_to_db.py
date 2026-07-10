"""Migrare MVP1 -> MVP2: copiaza datele din JSON in DB.

Ruleaza o singura data cand treci pe STORAGE_BACKEND=db, ca sa nu pierzi
produsele si conversatiile existente.

  python migrate_json_to_db.py
"""
import sys

from loguru import logger

import config
from adapters.storage.json_adapter import JSONAdapter

logger.remove()
logger.add(sys.stderr, level="INFO")


def main() -> None:
    json_store = JSONAdapter()
    db_store = config.build_storage()

    if type(db_store).__name__ != "DBAdapter":
        logger.error(
            "STORAGE_BACKEND nu e 'db'. Seteaza STORAGE_BACKEND=db in .env "
            "inainte de migrare."
        )
        return

    products = json_store.get_products()
    for p in products:
        db_store.save_product(p)
    logger.info("{} produse migrate.", len(products))

    conversations = json_store.get_conversations()
    for c in conversations:
        if not db_store.is_processed(
            c.get("olx_conversation_id", ""), c.get("buyer_message", "")
        ):
            db_store.log_conversation(c)
    logger.info("{} conversatii migrate.", len(conversations))

    logger.info("Gata. Statistici DB: {}", db_store.stats())


if __name__ == "__main__":
    main()
