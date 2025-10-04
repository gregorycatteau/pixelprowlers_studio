# ai_assistants/utils/context_cache.py

from functools import lru_cache

from .db_loader import get_agent_full_profile, get_agent_system_context, get_current_manifest


@lru_cache(maxsize=1)
def get_cached_manifest():
    """
    Retourne le manifeste courant depuis la base de données, en cache.
    """
    return get_current_manifest()


@lru_cache(maxsize=10)
def get_cached_agent_profile(agent_name: str):
    """
    Retourne le profil enrichi complet d’un agent donné (par nom), en cache.
    """
    return get_agent_full_profile(agent_name)


@lru_cache(maxsize=10)
def get_cached_agent_context(agent_name: str):
    """
    Retourne le contexte système enregistré d’un agent donné, en cache.
    """
    return get_agent_system_context(agent_name)
