"""Modele ORM SQLAlchemy pentru MVP2.

Aceleasi campuri ca schemele JSON din MVP1, ca trecerea JSON -> DB sa nu
schimbe nimic in core/. Campurile imbricate (attributes, faq, shipping,
keywords) sunt coloane JSON — merg identic pe SQLite si PostgreSQL.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(120), default="")
    subcategory: Mapped[str] = mapped_column(String(120), default="")
    price: Mapped[float] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(8), default="RON")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    condition: Mapped[str] = mapped_column(String(32), default="folosit")
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    faq: Mapped[list] = mapped_column(JSON, default=list)
    shipping: Mapped[dict] = mapped_column(JSON, default=dict)
    keywords: Mapped[list] = mapped_column(JSON, default=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "subcategory": self.subcategory,
            "price": self.price,
            "currency": self.currency,
            "stock": self.stock,
            "condition": self.condition,
            "description": self.description,
            "attributes": self.attributes or {},
            "faq": self.faq or [],
            "shipping": self.shipping or {},
            "keywords": self.keywords or [],
        }


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    olx_conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[str] = mapped_column(String(32))
    buyer_message: Mapped[str] = mapped_column(Text)
    bot_response: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="sent")
    buyer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ad_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "olx_conversation_id": self.olx_conversation_id,
            "product_id": self.product_id,
            "timestamp": self.timestamp,
            "buyer_message": self.buyer_message,
            "bot_response": self.bot_response,
            "status": self.status,
            "buyer_name": self.buyer_name,
            "ad_title": self.ad_title,
        }


class Job(Base):
    """Coada de joburi. Un mesaj nou de la cumparator devine un job.

    Ciclu de viata:
      pending -> processing -> done -> sending -> sent
                     |                     |
                     +--> failed <---------+
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    olx_conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    buyer_message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ad_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "olx_conversation_id": self.olx_conversation_id,
            "buyer_message": self.buyer_message,
            "status": self.status,
            "response_text": self.response_text,
            "product_id": self.product_id,
            "attempts": self.attempts,
            "error": self.error,
            "buyer_name": self.buyer_name,
            "ad_title": self.ad_title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Order(Base):
    """Stub pentru MVP2+ — comenzile nu sunt inca folosite de bot, dar
    tabelul exista ca schema DB sa fie completa (products/conversations/
    orders/jobs)."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    olx_conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    buyer_name: Mapped[str] = mapped_column(String(200), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="nou")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "olx_conversation_id": self.olx_conversation_id,
            "buyer_name": self.buyer_name,
            "quantity": self.quantity,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
