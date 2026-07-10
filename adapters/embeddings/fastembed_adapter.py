"""Embeddings locale prin FastEmbed (ONNX, fara PyTorch, fara API extern).

Modelul multilingv (~220MB) se descarca o singura data in data/models/ —
la `setup.bat`/`setup.sh` sau la prima folosire. Daca descarcarea sau
incarcarea esueaza, adaptorul intoarce None si botul functioneaza mai
departe doar cu potrivirea lexicala (fara matching semantic).
"""
import math
import warnings
from pathlib import Path

from loguru import logger

from adapters.embeddings.base import BaseEmbeddingsAdapter

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CACHE_DIR = "data/models"


class FastEmbedAdapter(BaseEmbeddingsAdapter):
    def __init__(self, model_name: str = MODEL_NAME, cache_dir: str = CACHE_DIR):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._failed = False  # nu reincerca la fiecare mesaj daca modelul nu merge

    def _load(self):
        if self._model is not None or self._failed:
            return self._model
        try:
            from fastembed import TextEmbedding

            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
            logger.info("Incarc modelul de embeddings {}...", self.model_name)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._model = TextEmbedding(
                    model_name=self.model_name, cache_dir=self.cache_dir
                )
            logger.info("Model de embeddings incarcat.")
        except Exception as e:
            self._failed = True
            logger.warning(
                "Embeddings indisponibile ({}) — folosesc doar potrivirea "
                "lexicala pentru FAQ.", e
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        model = self._load()
        if model is None or not texts:
            return None if model is None else []
        try:
            vectors = []
            for vec in model.embed(texts):
                values = [float(x) for x in vec]
                norm = math.sqrt(sum(x * x for x in values)) or 1.0
                vectors.append([x / norm for x in values])
            return vectors
        except Exception as e:
            logger.warning("Eroare la calculul embeddings: {}", e)
            return None


def warm_up() -> None:
    """Descarca/incarca modelul (apelat din setup, ca prima rulare sa fie rapida)."""
    adapter = FastEmbedAdapter()
    if adapter.embed(["test"]) is None:
        print("AVERTISMENT: modelul de embeddings nu a putut fi descarcat.")
        print("Botul va functiona, dar fara potrivirea semantica a FAQ-ului.")
    else:
        print("Model de embeddings pregatit.")


if __name__ == "__main__":
    warm_up()
