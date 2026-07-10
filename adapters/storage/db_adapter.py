"""Adaptor de stocare pe DB (SQLAlchemy) — MVP2.

Implementeaza acelasi contract ca JSONAdapter (BaseStorageAdapter) plus
metodele extra folosite de UI (save_product/delete_product/get_conversations)
si coada de joburi (BaseJobQueue). Se poate schimba cu JSONAdapter in
config.py fara sa atinga nimic din core/.

Ruleaza pe SQLite acum; pe PostgreSQL cand schimbi DATABASE_URL — zero cod.
"""
import uuid
from datetime import datetime, timezone

from loguru import logger

from adapters.storage.base import BaseJobQueue, BaseStorageAdapter
from adapters.storage.db import DEFAULT_URL, make_engine, make_session_factory
from adapters.storage.models import Conversation, Job, Product


class DBAdapter(BaseStorageAdapter, BaseJobQueue):
    def __init__(self, database_url: str = DEFAULT_URL):
        self.engine = make_engine(database_url)
        self.Session = make_session_factory(self.engine)
        logger.info("DBAdapter conectat: {}", database_url)

    # ------------------------------------------------------------------ #
    # produse
    # ------------------------------------------------------------------ #

    def get_products(self) -> list:
        with self.Session() as s:
            return [p.to_dict() for p in s.query(Product).all()]

    def get_product(self, product_id: str) -> dict | None:
        with self.Session() as s:
            p = s.get(Product, product_id)
            return p.to_dict() if p else None

    def save_product(self, product: dict) -> dict:
        fields = {
            "title", "category", "subcategory", "price", "currency", "stock",
            "condition", "description", "attributes", "faq", "shipping", "keywords",
        }
        with self.Session() as s:
            p = s.get(Product, product.get("id")) if product.get("id") else None
            if p is None:
                p = Product(id=product.get("id") or f"prod_{uuid.uuid4().hex[:6]}")
                s.add(p)
            for k in fields:
                if k in product:
                    setattr(p, k, product[k])
            s.commit()
            logger.info("Produs salvat: {}", p.id)
            return p.to_dict()

    def delete_product(self, product_id: str) -> None:
        with self.Session() as s:
            p = s.get(Product, product_id)
            if p:
                s.delete(p)
                s.commit()
                logger.info("Produs sters: {}", product_id)

    # ------------------------------------------------------------------ #
    # conversatii
    # ------------------------------------------------------------------ #

    def get_conversations(self) -> list:
        with self.Session() as s:
            return [c.to_dict() for c in s.query(Conversation).all()]

    def log_conversation(self, conversation: dict) -> None:
        with self.Session() as s:
            s.add(Conversation(
                id=conversation.get("id") or f"conv_{uuid.uuid4().hex[:8]}",
                olx_conversation_id=conversation["olx_conversation_id"],
                product_id=conversation.get("product_id"),
                timestamp=conversation.get("timestamp", ""),
                buyer_message=conversation.get("buyer_message", ""),
                bot_response=conversation.get("bot_response", ""),
                status=conversation.get("status", "sent"),
                buyer_name=conversation.get("buyer_name"),
                ad_title=conversation.get("ad_title"),
            ))
            s.commit()
            logger.info("Conversatie logata: {}", conversation.get("id"))

    def is_processed(self, olx_conversation_id: str, buyer_message: str) -> bool:
        """Sarim doar daca ultimul mesaj procesat din conversatie e identic —
        mesajele noi (chiar in conversatii vechi) primesc mereu raspuns."""
        with self.Session() as s:
            last = (
                s.query(Conversation)
                .filter_by(olx_conversation_id=olx_conversation_id)
                # timestamp e ISO-8601 (UTC), deci sortarea ca text e corecta
                .order_by(Conversation.timestamp.desc())
                .first()
            )
            return (
                last is not None
                and last.buyer_message == buyer_message
                and last.status == "sent"
            )

    def mark_conversation_status(
        self, olx_conversation_id: str, buyer_message: str, status: str
    ) -> None:
        with self.Session() as s:
            conversation = (
                s.query(Conversation)
                .filter_by(
                    olx_conversation_id=olx_conversation_id,
                    buyer_message=buyer_message,
                )
                .order_by(Conversation.timestamp.desc())
                .first()
            )
            if conversation is not None:
                conversation.status = status
                s.commit()
                logger.info("Status conversatie {} -> {}.", conversation.id, status)

    # ------------------------------------------------------------------ #
    # coada de joburi (BaseJobQueue)
    # ------------------------------------------------------------------ #

    _ACTIVE = ("pending", "processing", "done", "sending")

    def enqueue_job(
        self,
        olx_conversation_id: str,
        buyer_message: str,
        buyer_name: str | None = None,
        ad_title: str | None = None,
    ) -> str:
        with self.Session() as s:
            job = Job(
                id=f"job_{uuid.uuid4().hex[:10]}",
                olx_conversation_id=olx_conversation_id,
                buyer_message=buyer_message,
                status="pending",
                buyer_name=buyer_name,
                ad_title=ad_title,
            )
            s.add(job)
            s.commit()
            logger.info("Job adaugat: {} (conv {})", job.id, olx_conversation_id)
            return job.id

    def has_active_job(self, olx_conversation_id: str) -> bool:
        with self.Session() as s:
            return s.query(Job).filter(
                Job.olx_conversation_id == olx_conversation_id,
                Job.status.in_(self._ACTIVE),
            ).first() is not None

    def claim_next_job(self) -> dict | None:
        return self._claim(from_status="pending", to_status="processing")

    def complete_job(self, job_id: str, response_text: str,
                     product_id: str | None) -> None:
        with self.Session() as s:
            job = s.get(Job, job_id)
            if job:
                job.status = "done"
                job.response_text = response_text
                job.product_id = product_id
                s.commit()

    def fail_job(self, job_id: str, error: str) -> None:
        with self.Session() as s:
            job = s.get(Job, job_id)
            if job:
                job.status = "failed"
                job.attempts += 1
                job.error = error
                s.commit()

    def claim_job_to_send(self) -> dict | None:
        return self._claim(from_status="done", to_status="sending")

    def mark_job_sent(self, job_id: str) -> None:
        with self.Session() as s:
            job = s.get(Job, job_id)
            if job:
                job.status = "sent"
                s.commit()

    def _claim(self, from_status: str, to_status: str) -> dict | None:
        """Ia atomic urmatorul job intr-o stare data si il muta in alta.

        with_for_update(skip_locked) da concurenta reala pe PostgreSQL;
        pe SQLite e no-op, dar tranzactia de scriere serializeaza oricum,
        deci ramane corect si cu mai multi workeri.
        """
        with self.Session() as s:
            q = (
                s.query(Job)
                .filter(Job.status == from_status)
                .order_by(Job.created_at.asc())
            )
            try:
                job = q.with_for_update(skip_locked=True).first()
            except Exception:
                job = q.first()  # backend fara suport FOR UPDATE
            if job is None:
                return None
            job.status = to_status
            if to_status == "processing":
                job.attempts += 1
            s.commit()
            return job.to_dict()

    # ------------------------------------------------------------------ #
    # utilitar: import din JSON (migrare MVP1 -> MVP2)
    # ------------------------------------------------------------------ #

    def import_products(self, products: list) -> int:
        for p in products:
            self.save_product(p)
        return len(products)

    def stats(self) -> dict:
        with self.Session() as s:
            return {
                "products": s.query(Product).count(),
                "conversations": s.query(Conversation).count(),
                "jobs_pending": s.query(Job).filter_by(status="pending").count(),
                "jobs_done": s.query(Job).filter_by(status="done").count(),
                "jobs_sent": s.query(Job).filter_by(status="sent").count(),
                "jobs_failed": s.query(Job).filter_by(status="failed").count(),
            }
