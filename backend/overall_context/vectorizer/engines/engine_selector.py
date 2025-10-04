import logging
import os

from overall_context.vectorizer.engines.base import Embedder
from overall_context.vectorizer.engines.openai_embedder import OpenAIEmbedder

logger = logging.getLogger(__name__)

MODES = ["low", "secure", "fortress"]


def get_embedder(mode: str = "low") -> Embedder:
    """
    Retourne l'embedder en fonction du mode de sécurité.
    - low : rapide, fluide, utilise OpenAI si dispo
    - secure : local prioritaire, fallback OpenAI
    - fortress : local only, offline exigé
    """
    mode = mode.lower()
    if mode not in MODES:
        raise ValueError(f"Mode inconnu : {mode}. Attendus : {MODES}")

    if mode == "low":
        try:
            logger.info("[EMBEDDER] Mode LOW → OpenAIEmbedder")
            return OpenAIEmbedder()
        except Exception as e:
            logger.warning(f"[EMBEDDER] ⚠️ Fallback to local: {e}")
            return LocalEmbedder()

    elif mode == "secure":
        try:
            logger.info("[EMBEDDER] Mode SECURE → LocalEmbedder (prioritaire)")
            return LocalEmbedder()
        except Exception as e:
            logger.warning(f"[EMBEDDER] ⚠️ Local fail. Fallback to OpenAI: {e}")
            return OpenAIEmbedder()

    elif mode == "fortress":
        try:
            # Fortress n'autorise AUCUNE dépendance externe
            logger.info("[EMBEDDER] Mode FORTRESS → LocalEmbedder only (airgap enforced)")
            return LocalEmbedder()
        except Exception as e:
            logger.critical(f"[EMBEDDER] 🛑 Fortress mode failed: {e}")
            raise RuntimeError("Fortress mode exige un moteur local fonctionnel.")
