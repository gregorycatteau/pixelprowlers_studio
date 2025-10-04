from typing import List

from overall_context.vectorizer.engines.base import Embedder
from sentence_transformers import SentenceTransformer


class LocalEmbedder(Embedder):
    def __init__(self, model_name="intfloat/multilingual-e5-small"):
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
