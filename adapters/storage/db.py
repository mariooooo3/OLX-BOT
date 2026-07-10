"""Engine + session factory SQLAlchemy.

Un singur loc care citeste DATABASE_URL. Trecerea SQLite -> PostgreSQL
inseamna DOAR schimbarea acestui URL in .env; codul ramane neschimbat.

Exemple:
  sqlite:///data/olxbot.db                      (implicit, zero instalari)
  postgresql+psycopg://user:pass@host:5432/db   (cand vrei Postgres)
"""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from adapters.storage.models import Base

DEFAULT_URL = "sqlite:///data/olxbot.db"

# coloane adaugate dupa prima versiune a schemei — create_all nu face ALTER,
# deci bazele existente primesc coloanele noi aici (ADD COLUMN e suportat
# identic de SQLite si PostgreSQL)
_SCHEMA_UPGRADES = {
    "conversations": {
        "buyer_name": "VARCHAR(200)",
        "ad_title": "VARCHAR(500)",
    },
    "jobs": {
        "buyer_name": "VARCHAR(200)",
        "ad_title": "VARCHAR(500)",
    },
}


def _apply_schema_upgrades(engine: Engine) -> None:
    inspector = inspect(engine)
    for table, columns in _SCHEMA_UPGRADES.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        with engine.begin() as conn:
            for name, ddl_type in columns.items():
                if name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")
                    )


def make_engine(database_url: str = DEFAULT_URL) -> Engine:
    if database_url.startswith("sqlite:///"):
        # asiguram existenta directorului fisierului SQLite
        rel = database_url.replace("sqlite:///", "", 1)
        Path(rel).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: engine folosit din thread-ul botului
        engine = create_engine(
            database_url, connect_args={"check_same_thread": False}, future=True
        )
    else:
        engine = create_engine(database_url, pool_pre_ping=True, future=True)
    Base.metadata.create_all(engine)
    _apply_schema_upgrades(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
