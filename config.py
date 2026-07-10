"""Configurare centrala. Alegerea adaptoarelor se face 100% din .env.

MVP1 -> MVP2 = doar variabile de mediu, zero cod modificat:
  LLM_BACKEND=groq | ollama
  STORAGE_BACKEND=json | db
  DATABASE_URL=sqlite:///data/olxbot.db  (sau postgresql+psycopg://...)
  USE_QUEUE=false | true   (coada de joburi + workeri separati)
"""
import os

from dotenv import load_dotenv

# override=True: cheia din .env-ul proiectului are prioritate fata de
# variabilele globale Windows (ex. GROQ_API_KEY setat pentru alt proiect)
load_dotenv(override=True)

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "45"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
OLX_EMAIL = os.environ.get("OLX_EMAIL", "")
OLX_PASSWORD = os.environ.get("OLX_PASSWORD", "")

LLM_BACKEND = os.environ.get("LLM_BACKEND", "groq").lower()
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "json").lower()
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/olxbot.db")
USE_QUEUE = os.environ.get("USE_QUEUE", "false").lower() in ("1", "true", "yes")


def build_llm():
    if LLM_BACKEND == "ollama":
        from adapters.llm.ollama_adapter import OllamaAdapter
        return OllamaAdapter()
    from adapters.llm.groq_adapter import GroqAdapter
    return GroqAdapter()


def build_storage(account_id: str | None = None):
    """Stocarea datelor. Cu account_id, datele (produse, conversatii) sunt
    izolate per cont OLX in data/accounts/<account_id>/.

    Backend-ul db nu are inca separare per cont (tabelele sunt globale) —
    de adaugat o coloana account_id cand se trece pe db cu mai multe conturi.
    """
    if STORAGE_BACKEND == "db":
        from adapters.storage.db_adapter import DBAdapter
        return DBAdapter(DATABASE_URL)
    from adapters.storage.json_adapter import JSONAdapter
    if account_id:
        return JSONAdapter(data_dir=f"data/accounts/{account_id}")
    return JSONAdapter()


# Adaptoarele se construiesc lazy (build_llm / build_storage) de fiecare
# proces care are nevoie de ele. Fara instante la import: serverul porneste
# si fara GROQ_API_KEY — cheia e necesara abia cand pornesti efectiv botul.
