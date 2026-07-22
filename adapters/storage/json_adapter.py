import json
import os
import tempfile
from pathlib import Path

from loguru import logger

from adapters.storage.base import BaseStorageAdapter


class JSONAdapter(BaseStorageAdapter):
    """Stocare pe fisiere JSON locale: products.json (citire) si
    conversations.json (log, creat automat)."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.products_path = self.data_dir / "products.json"
        self.conversations_path = self.data_dir / "conversations.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_products(self) -> list:
        if not self.products_path.exists():
            # debug, nu warning: cu mai multe conturi, unul cu catalogul inca
            # gol e o stare normala, nu o problema — altfel umple logul cu
            # avertismente la fiecare ciclu de polling
            logger.debug("Nu exista {} — catalog gol.", self.products_path)
            return []
        with open(self.products_path, encoding="utf-8") as f:
            return json.load(f).get("products", [])

    def save_product(self, product: dict) -> dict:
        """Adauga sau actualizeaza un produs in products.json (folosit de UI)."""
        products = self.get_products()
        idx = next(
            (i for i, p in enumerate(products) if p.get("id") == product.get("id")),
            None,
        )
        if idx is None:
            products.append(product)
        else:
            products[idx] = product
        self._write_atomic(self.products_path, {"products": products})
        logger.info("Produs salvat: {}", product.get("id"))
        return product

    def delete_product(self, product_id: str) -> None:
        products = [p for p in self.get_products() if p.get("id") != product_id]
        self._write_atomic(self.products_path, {"products": products})
        logger.info("Produs sters: {}", product_id)

    def get_conversations(self) -> list:
        """Toate conversatiile logate (folosit de UI)."""
        return self._read_conversations()["conversations"]

    def log_conversation(self, conversation: dict) -> None:
        data = self._read_conversations()
        data["conversations"].append(conversation)
        self._write_atomic(self.conversations_path, data)
        logger.info("Conversatie logata: {}", conversation.get("id"))

    def is_processed(self, olx_conversation_id: str, buyer_message: str) -> bool:
        """Sarim doar daca ultimul mesaj procesat din conversatie e identic —
        mesajele noi (chiar in conversatii vechi) primesc mereu raspuns."""
        entries = [
            c for c in self._read_conversations()["conversations"]
            if c.get("olx_conversation_id") == olx_conversation_id
        ]
        # intrarile se adauga cronologic, deci ultima e cea mai recenta
        return (
            bool(entries)
            and entries[-1].get("buyer_message") == buyer_message
            and entries[-1].get("status", "sent") == "sent"
        )

    def mark_conversation_status(
        self, olx_conversation_id: str, buyer_message: str, status: str
    ) -> None:
        data = self._read_conversations()
        for conversation in reversed(data["conversations"]):
            if (
                conversation.get("olx_conversation_id") == olx_conversation_id
                and conversation.get("buyer_message") == buyer_message
            ):
                conversation["status"] = status
                self._write_atomic(self.conversations_path, data)
                logger.info(
                    "Status conversatie {} -> {}.",
                    conversation.get("id"),
                    status,
                )
                return

    def _read_conversations(self) -> dict:
        if not self.conversations_path.exists():
            return {"conversations": []}
        with open(self.conversations_path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_atomic(path: Path, data: dict) -> None:
        # scriere in fisier temporar + replace, ca un crash sa nu corupa logul
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
