from abc import ABC, abstractmethod


class BaseEmbeddingsAdapter(ABC):
    """Contract pentru orice adaptor de embeddings (FastEmbed in MVP)."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Vectorii (normalizati L2) pentru fiecare text, in aceeasi ordine.

        Returneaza None daca embeddings nu sunt disponibile (model lipsa,
        descarcare esuata) — apelantul degradeaza la potrivirea lexicala.
        """
