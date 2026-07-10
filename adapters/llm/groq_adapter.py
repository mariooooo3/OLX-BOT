import os

from groq import Groq
from loguru import logger

from adapters.llm.base import BaseLLMAdapter


class GroqAdapter(BaseLLMAdapter):
    """Adaptor LLM peste Groq API."""

    # llama3-8b-8192 din specul initial a fost retras de Groq;
    # llama-3.1-8b-instant e inlocuitorul recomandat
    DEFAULT_MODEL = "llama-3.1-8b-instant"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("GROQ_MODEL", self.DEFAULT_MODEL)
        self._client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        logger.debug("Apel Groq ({}) ...", self.model)
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=512,
        )
        reply = (completion.choices[0].message.content or "").strip()
        logger.debug("Raspuns Groq ({} caractere)", len(reply))
        return reply
