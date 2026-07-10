"""Adaptor LLM peste Ollama (local) — MVP2.

Aceeasi interfata ca GroqAdapter (BaseLLMAdapter), deci se schimba doar in
config.py. Nu depinde de niciun SDK: vorbeste direct cu API-ul HTTP Ollama
(`/api/chat`), asa ca nu instaleaza nimic pana nu il activezi efectiv.

Activare (cand vrei):
  1. instalezi Ollama + un model (ex. `ollama pull llama3.1:8b`)
  2. LLM_BACKEND=ollama in .env
"""
import os

import requests
from loguru import logger

from adapters.llm.base import BaseLLMAdapter


class OllamaAdapter(BaseLLMAdapter):
    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: int = 120,
    ):
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        logger.debug("Apel Ollama ({}) ...", self.model)
        resp = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.4},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        reply = (resp.json().get("message", {}).get("content") or "").strip()
        logger.debug("Raspuns Ollama ({} caractere)", len(reply))
        return reply
