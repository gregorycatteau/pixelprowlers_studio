# -*- coding: utf-8 -*-
"""
S9 — Telemetry Intelligence tests

Couvre:
- Aggregation JSONL format (write_aggregated_jsonl)
- Trends detection (risk_operational_score borné [0,1])
- Gatekeeper adaptive threshold (±10%)
- Journal seal_day integrity (hash-chain + HMAC)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# A) Aggregation output format
# ──────────────────────────────────────────────────────────────────────────────
def test_telemetry_aggregation_output_format(tmp_path: Path) -> None:
    from studio_core.telemetry.aggregator import TelemetryRecord, write_aggregated_jsonl

    # Fabriquer quelques enregistrements normalisés
    now = int(datetime.now(tz=timezone.utc).timestamp())
    records = [
        TelemetryRecord(
            timestamp=now, metric="monitor_event", value=1.0, source="monitor", severity="INFO"
        ),
        TelemetryRecord(
            timestamp=now, metric="alerts_rules_crit", value=2.0, source="alerts", severity="INFO"
        ),
        TelemetryRecord(
            timestamp=now,
            metric="resilience_event",
            value=1.0,
            source="resilience",
            severity="WARN",
        ),
    ]
    # Écrire JSONL dans un dossier ops isolé
    out = write_aggregated_jsonl(
        records, output_dir=tmp_path / "ops", when=datetime.now(tz=timezone.utc)
    )
    assert out.exists(), "Le fichier JSONL agrégé doit exister"
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3, "Chaque enregistrement doit produire une ligne JSON"

    # Valider structure de base
    obj = json.loads(lines[0])
    for key in ("timestamp", "metric", "value", "source", "severity"):
        assert key in obj, f"Champ manquant dans JSONL: {key}"


# ──────────────────────────────────────────────────────────────────────────────
# B) Trends detection / score
# ──────────────────────────────────────────────────────────────────────────────
def test_trend_detection_thresholds() -> None:
    from studio_core.telemetry.trends import summarize_trends_from_records

    # Fabriquer un jeu "records" minimal (dicts) sur plusieurs heures
    now = int(datetime(2025, 1, 1, 12, tzinfo=timezone.utc).timestamp())
    records: List[Dict[str, Any]] = []
    # 6 points horaires: 3 INFO, 2 WARN, 1 CRIT
    severities = ["INFO", "INFO", "WARN", "INFO", "WARN", "CRIT"]
    for i, sev in enumerate(severities):
        records.append(
            {
                "timestamp": now + i * 3600,
                "severity": sev,
                "metric": "dummy",
                "value": 1.0,
                "source": "test",
            }
        )

    summary = summarize_trends_from_records(records, window=timedelta(hours=6))
    # Valeurs présentes et bornées
    assert 0.0 <= summary.risk_operational_score <= 1.0
    assert summary.window_seconds == 6 * 3600
    # Totaux cohérents
    assert summary.totals["events"] == len(severities)
    assert summary.totals["crit"] == 1
    assert summary.totals["warn"] == 2
    assert summary.totals["info"] == 3


# ──────────────────────────────────────────────────────────────────────────────
# C) Gatekeeper adaptive threshold (±10%)
# ──────────────────────────────────────────────────────────────────────────────
def test_gatekeeper_adaptive_threshold_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.eotp.gatekeeper as gate

    # Fixer le seuil de base (module-level)
    monkeypatch.setattr(gate, "GATE_RISK_THRESHOLD", 0.70, raising=False)

    # Cas 1: score >= 0.7 → renforcer +10%
    monkeypatch.setattr(gate, "get_latest_risk_score", lambda: 0.80, raising=False)
    eff = gate.get_adaptive_gate_threshold()
    assert eff == pytest.approx(0.77, rel=1e-6)

    # Cas 2: score <= 0.3 → relâcher -10%
    monkeypatch.setattr(gate, "get_latest_risk_score", lambda: 0.20, raising=False)
    eff = gate.get_adaptive_gate_threshold()
    assert eff == pytest.approx(0.63, rel=1e-6)

    # Cas 3: score None → inchangé
    monkeypatch.setattr(gate, "get_latest_risk_score", lambda: None, raising=False)
    eff = gate.get_adaptive_gate_threshold()
    assert eff == pytest.approx(0.70, rel=1e-6)


# ──────────────────────────────────────────────────────────────────────────────
# D) Journal seal_day integrity (hash-chain + HMAC)
# ──────────────────────────────────────────────────────────────────────────────
def test_seal_day_integrity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from studio_core.obs import journal

    # Créer un journal isolé
    log_file = tmp_path / "auth_journal.log"

    # Append quelques événements PII-safe
    journal.append_event_to(str(log_file), {"source": "test", "event": "a"})
    journal.append_event_to(str(log_file), {"source": "test", "event": "b"})
    journal.append_event_to(str(log_file), {"source": "test", "event": "c"})

    # Sceller avec clé HMAC locale
    key = "s9-local-key"
    proof_path = journal.seal_day(signing_key=key, file_path=str(log_file))
    assert proof_path.exists(), "La preuve de scellement doit exister"

    # Vérifier la chaîne
    ok, checked, err = journal.verify_chain(str(log_file), deep=True)
    assert ok, f"verify_chain doit être OK (err={err})"
    assert checked >= 3

    # Vérifier la signature HMAC du payload (date/last_hash/count)
    text = proof_path.read_text(encoding="utf-8")
    # Extraire lignes utiles
    # payload:
    #   date:YYYY-MM-DD
    #   last_hash:<hex>
    #   count:N
    #   hmac_sha256:<hex>
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    payload_lines = []  # jusqu'à 'count'
    hmac_line = ""
    for ln in lines:
        if ln.startswith("hmac_sha256:"):
            hmac_line = ln
            break
        payload_lines.append(ln + "\n")
    assert hmac_line, "Ligne hmac_sha256 manquante"
    expected_payload = "".join(payload_lines)
    _, sig_hex = hmac_line.split(":", 1)
    sig_hex = sig_hex.strip()

    computed = hmac.new(
        key.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert sig_hex == computed, "La signature HMAC ne correspond pas au payload"


# ──────────────────────────────────────────────────────────────────────────────
# Markers/selection helpers
# ──────────────────────────────────────────────────────────────────────────────
pytestmark = pytest.mark.django_db(transaction=False)
