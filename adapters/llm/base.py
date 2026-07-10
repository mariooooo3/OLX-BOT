from abc import ABC, abstractmethod


class BaseLLMAdapter(ABC):
    """Contract pentru orice adaptor LLM (Groq in MVP1, Ollama in MVP2)."""

    @abstractmethod
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        pass
