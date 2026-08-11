"""Adaptor de stocare pe DB (SQLAlchemy) — MVP2.

Implementeaza acelasi contract ca JSONAdapter (BaseStorageAdapter) plus
metodele extra folosite de UI (save_product/delete_product/get_conversations)
si coada de joburi (BaseJobQueue). Se poate schimba cu JSONAdapter in
config.py fara sa atinga nimic din core/.

Ruleaza pe SQLite acum; pe PostgreSQL cand schimbi DATABASE_URL — zero cod.

Separare pe conturi (`account_id`): fiecare instanta poate fi legata de UN
cont OLX (`DBAdapter(url, account_id="acc_x")`), la fel cum JSONAdapter e
legat de folderul lui. Fara account_id (implicit — compatibilitate cu
instalarile MVP2 dintr-un singur cont), adaptorul vede si scrie TOT, exact
ca inainte de aceasta separare.
"""
import uuid
from datetime import datetime, timezone

from loguru import logger

from adapters.storage.base import BaseJobQueue, BaseStorageAdapter
from adapters.storage.db import DEFAULT_URL, make_engine, make_session_factory
from adapters.storage.models import Conversation, FinanceTransaction, Job, Product


class DBAdapter(BaseStorageAdapter, BaseJobQueue):
    def __init__(self, database_url: str = DEFAULT_URL, account_id: str | None = None):
        self.engine = make_engine(database_url)
        self.Session = make_session_factory(self.engine)
        self.account_id = account_id
        logger.info(
            "DBAdapter conectat: {} (cont: {})", database_url, account_id or "toate"
        )

    def _scope(self, query):
        """Filtreaza dupa contul acestei instante — doar daca instanta ARE
        un cont asociat. Fara account_id (compatibilitate), interogarile
        raman neschimbate fata de comportamentul dinainte de separare."""
        if self.account_id is None:
            return query
        return query.filter_by(account_id=self.account_id)

    def _check_ownership(self, row, kind: str) -> None:
        """Ridica eroare in loc sa suprascrie tacit randul altui cont.

        `id`-urile sunt cheie primara GLOBALA in DB (spre deosebire de
        JSONAdapter, unde fiecare cont are propriul fisier — separarea e
        fizica, nu poate coliziona). O potrivire de id intre doua conturi e
        extrem de improbabila la scara acestei aplicatii, dar daca s-ar
        intampla (sau un client trimite din greseala id-ul altui cont), mai
        bine o eroare zgomotoasa decat o suprascriere tacuta a datelor
        altcuiva.
        """
        if (
            row is not None
            and self.account_id is not None
            and row.account_id is not None
            and row.account_id != self.account_id
        ):
            raise ValueError(
                f"{kind} {row.id!r} apartine altui cont ({row.account_id!r}), "
                f"nu contului curent ({self.account_id!r})."
            )

    # ------------------------------------------------------------------ #
    # produse
    # ------------------------------------------------------------------ #

    def get_products(self) -> list:
        with self.Session() as s:
            return [p.to_dict() for p in self._scope(s.query(Product)).all()]

    def get_product(self, product_id: str) -> dict | None:
        with self.Session() as s:
            p = s.get(Product, product_id)
            if p is None:
                return None
            self._check_ownership(p, "Produsul")
            return p.to_dict()

    def save_product(self, product: dict) -> dict:
        fields = {
            "title", "category", "subcategory", "price", "currency", "stock",
            "condition", "description", "attributes", "faq", "shipping", "keywords",
        }
        with self.Session() as s:
            p = s.get(Product, product.get("id")) if product.get("id") else None
            self._check_ownership(p, "Produsul")
            if p is None:
                p = Product(
                    id=product.get("id") or f"prod_{uuid.uuid4().hex[:6]}",
                    account_id=self.account_id,
                )
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
                self._check_ownership(p, "Produsul")
                s.delete(p)
                s.commit()
                logger.info("Produs sters: {}", product_id)

    # ------------------------------------------------------------------ #
    # gestiune financiara
    # ------------------------------------------------------------------ #

    def get_finance_transactions(self, product_id: str | None = None) -> list:
        with self.Session() as s:
            query = self._scope(s.query(FinanceTransaction))
            if product_id is not None:
                query = query.filter_by(product_id=product_id)
            return [item.to_dict() for item in query.all()]

    def save_finance_transaction(self, transaction: dict) -> dict:
        fields = {
            "product_id",
            "kind",
            "currency",
            "quantity",
            "unit_price",
            "vat_rate",
            "vat_included",
            "vat_deductible",
            "occurred_at",
            "note",
            "created_at",
        }
        with self.Session() as s:
            item = s.get(FinanceTransaction, transaction.get("id"))
            self._check_ownership(item, "Tranzactia")
            if item is None:
                item = FinanceTransaction(
                    id=transaction.get("id") or f"tx_{uuid.uuid4().hex[:10]}",
                    account_id=self.account_id,
                )
                s.add(item)
            for field in fields:
                if field in transaction:
                    setattr(item, field, transaction[field])
            s.commit()
            logger.info("Tranzactie financiara salvata: {}", item.id)
            return item.to_dict()

    def delete_finance_transaction(self, transaction_id: str) -> None:
        with self.Session() as s:
            item = s.get(FinanceTransaction, transaction_id)
            if item is not None:
                self._check_ownership(item, "Tranzactia")
                s.delete(item)
                s.commit()
                logger.info("Tranzactie financiara stearsa: {}", transaction_id)

    # ------------------------------------------------------------------ #
    # conversatii
    # ------------------------------------------------------------------ #

    def get_conversations(self) -> list:
        with self.Session() as s:
            return [c.to_dict() for c in self._scope(s.query(Conversation)).all()]

    def log_conversation(self, conversation: dict) -> None:
        with self.Session() as s:
            s.add(Conversation(
                id=conversation.get("id") or f"conv_{uuid.uuid4().hex[:8]}",
                account_id=self.account_id,
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
                self._scope(s.query(Conversation))
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
                self._scope(s.query(Conversation))
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
                account_id=self.account_id,
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
            return self._scope(s.query(Job)).filter(
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
                self._check_ownership(job, "Jobul")
                job.status = "done"
                job.response_text = response_text
                job.product_id = product_id
                s.commit()

    def fail_job(self, job_id: str, error: str) -> None:
        with self.Session() as s:
            job = s.get(Job, job_id)
            if job:
                self._check_ownership(job, "Jobul")
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
                self._check_ownership(job, "Jobul")
                job.status = "sent"
                s.commit()

    def _claim(self, from_status: str, to_status: str) -> dict | None:
        """Ia atomic urmatorul job intr-o stare data si il muta in alta,
        DOAR din coada contului acestei instante (daca are unul asociat).

        with_for_update(skip_locked) da concurenta reala pe PostgreSQL;
        pe SQLite e no-op, dar tranzactia de scriere serializeaza oricum,
        deci ramane corect si cu mai multi workeri.
        """
        with self.Session() as s:
            q = (
                self._scope(s.query(Job))
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
        """Statistici — ale contului acestei instante daca are unul asociat,
        altfel globale (toate conturile din DB)."""
        with self.Session() as s:
            return {
                "products": self._scope(s.query(Product)).count(),
                "conversations": self._scope(s.query(Conversation)).count(),
                "jobs_pending": self._scope(s.query(Job)).filter_by(status="pending").count(),
                "jobs_done": self._scope(s.query(Job)).filter_by(status="done").count(),
                "jobs_sent": self._scope(s.query(Job)).filter_by(status="sent").count(),
                "jobs_failed": self._scope(s.query(Job)).filter_by(status="failed").count(),
            }
