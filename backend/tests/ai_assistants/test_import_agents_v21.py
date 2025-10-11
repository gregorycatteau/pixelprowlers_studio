import json
from pathlib import Path

import pytest
from ai_assistants.models import AgentProfile
from django.core.management import call_command
from django.core.management.base import CommandError


def _manifest(slug: str, name: str) -> dict:
    return {
        "schema_version": "2.1.0",
        "profile_version": "1.0.0",
        "identity": {
            "name": name,
            "slug": slug,
            "alias": name,
            "description": f"Description {name}",
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
                "max_eur_per_day": 1.0,
                "hard_stop_on_exceed": True,
                "exhaust_local_first": True,
            },
        },
        "security": {
            "data_minimization": True,
            "encryption_required": True,
            "anonymization_supported": True,
            "incident_alert_level": "medium",
            "forbidden_operations": ["write_secrets"],
            "isolation_level": "sandboxed",
        },
        "observability": {
            "logs": {"fields": []},
            "metrics": [],
            "alarms": [],
            "audit_trail": {"enabled": False, "retention_days": 0},
        },
        "gates": {
            "preflight": [],
            "go_live": [],
            "rollback_plan": "disable agent",
        },
        "tools": [
            {
                "name": "code_interpreter",
                "description": "Analyse de code",
                "parameters_schema": {"type": "object"},
                "returns": "string",
            }
        ],
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.mark.django_db
@pytest.mark.agents
def test_import_v21_success(tmp_path):
    manifest = _manifest("alice", "Alice")
    json_path = tmp_path / "alice_agent.json"
    _write_json(json_path, manifest)

    call_command("import_agents", "--dir", str(tmp_path))

    agent = AgentProfile.objects.get(slug="alice")
    assert agent.manifest_json["identity"]["name"] == "Alice"


@pytest.mark.django_db
@pytest.mark.agents
def test_import_v21_detects_immutable_change(tmp_path):
    manifest = _manifest("bob", "Bob")
    json_path = tmp_path / "bob_agent.json"
    _write_json(json_path, manifest)
    call_command("import_agents", "--dir", str(tmp_path))

    manifest["identity"]["name"] = "Bob Nouveau"
    _write_json(json_path, manifest)

    with pytest.raises(CommandError) as exc:
        call_command("import_agents", "--dir", str(tmp_path))
    assert "immuables" in str(exc.value)


@pytest.mark.django_db
@pytest.mark.agents
def test_import_accepts_legacy_payload(tmp_path):
    legacy_payload = {
        "name": "Legacy",
        "description": "Agent legacy",
        "model": "gpt-4o",
        "temperature": 0.4,
        "instructions": "Tu es Legacy",
        "tools": [],
    }
    json_path = tmp_path / "legacy_agent.json"
    _write_json(json_path, legacy_payload)

    call_command("import_agents", "--dir", str(tmp_path))

    agent = AgentProfile.objects.get(slug="legacy")
    assert agent.name == "Legacy"
    assert agent.manifest_json["schema_version"] == "2.1.0"
