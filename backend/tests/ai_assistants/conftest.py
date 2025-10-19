import time

import pytest
from ai_assistants.models import AgentProfile, DojoAgent
from ai_assistants.utils.agent_schema import compute_manifest_hash
from ai_assistants.views import GATE_SESSION_KEY, GATE_WHEN_KEY
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache as django_cache
from django.middleware.csrf import get_token
from django.test import Client
from django.urls import reverse


@pytest.fixture(autouse=True)
def clear_cache():
    django_cache.clear()
    yield
    django_cache.clear()


@pytest.fixture
def superuser(db):
    user_model = get_user_model()
    return user_model.objects.create_superuser(
        username="security_ops",
        email="security.ops@example.com",
        password="Password123!",
    )


def _default_manifest(slug: str, name: str) -> dict:
    return {
        "schema_version": "2.1.0",
        "profile_version": "1.0.0",
        "identity": {
            "name": name,
            "slug": slug,
            "alias": name,
            "description": f"Profil pour {name}",
        },
        "communication_style": {
            "tone": "professionnel",
            "sentence_length": "moyenne",
            "language_level": "accessible-expert",
            "metaphor_usage": "modérée",
            "emoji_usage": False,
            "disclaimers": [],
        },
        "model_policy": {
            "provider_order": ["premium", "mid", "local"],
            "allowed_models": {"premium": ["gpt-4o"], "mid": [], "local": []},
            "premium_unlock_required": True,
            "caps": {"daily_tokens_in": 200000, "daily_tokens_out": 200000},
            "latency_slo_ms": 8000,
            "retries": 1,
            "fallback": {"on_timeout": "mid", "on_policy_denied": "mid"},
            "rate_limits": {"rpm": 30, "rph": 1000},
            "cache_policy": {"enabled": False, "ttl_seconds": 0},
            "budget_policy": {
                "max_eur_per_day": 3.0,
                "hard_stop_on_exceed": True,
                "exhaust_local_first": True,
            },
        },
        "security": {
            "data_minimization": True,
            "encryption_required": True,
            "anonymization_supported": True,
            "incident_alert_level": "medium",
        },
        "observability": {
            "log_retention_days": 30,
            "metrics_collected": ["latency_ms", "tokens_in", "tokens_out"],
            "anomaly_detection": False,
        },
        "gates": {"preflight": {"enabled": False}, "go_live": {"enabled": False}},
        "metadata": {"is_active": True},
        "tools": [],
    }


@pytest.fixture
def agent_profile(db):
    slug = "bruce"
    manifest = _default_manifest(slug, "Bruce")
    return AgentProfile.objects.create(
        slug=slug,
        name="Bruce",
        alias="Bruce",
        description="Gardien des données",
        schema_version="2.1.0",
        profile_version="1.0.0",
        model="gpt-4o",
        temperature=0.4,
        communication_style="professionnel",
        is_active=True,
        manifest_json=manifest,
        manifest_hash_sha256=compute_manifest_hash(manifest),
    )


@pytest.fixture
def dojo_agent(db):
    return DojoAgent.objects.create(
        slug="orchestrator",
        title="Orchestrator",
        description="Agent de test",
        capabilities={"tier": "mock"},
        is_active=True,
    )


@pytest.fixture
def client_logged(superuser, agent_profile):
    client = Client(enforce_csrf_checks=True)
    client.force_login(superuser)
    # Hit whoami to set csrf cookie
    client.get(reverse("api_auth_whoami"))
    session = client.session
    session[GATE_SESSION_KEY] = True
    session[GATE_WHEN_KEY] = time.time()
    session.save()
    return client


@pytest.fixture
def csrftoken(client_logged):
    response = client_logged.get(reverse("api_auth_whoami"))
    token = get_token(response.wsgi_request)
    client_logged.cookies[settings.CSRF_COOKIE_NAME] = token
    return token
