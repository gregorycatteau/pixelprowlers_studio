# -*- coding: utf-8 -*-
"""
studio_core.metrics
-------------------

Mini-registre de métriques compatible Prometheus (export texte).

Objectifs:
- Fournir des compteurs et jauges thread‑safe (Counter/Gauge).
- Support des labels (dimensions) et d’un export texte Prometheus stable.
- Aucune dépendance externe.

Exemples rapides:

    from studio_core.metrics import REGISTRY

    # Compteur simple, sans labels
    login_ok = REGISTRY.counter("pp_login_ok", "Logins (clients) réussis")
    login_ok.inc()

    # Compteur avec labels
    logins = REGISTRY.counter("pp_login_total", "Logins par realm et décision", label_names=("realm", "decision"))
    logins.inc({"realm": "clients", "decision": "ok"})
    logins.inc({"realm": "clients", "decision": "fail"}, value=2)

    # Export Prometheus (texte)
    print(REGISTRY.to_prometheus_text())

Notes:
- Les labels passés à `.inc({...})` doivent exactement correspondre aux `label_names`
  déclarés pour la métrique (ordre quelconque, noms stricts).
- Les noms de métriques et de labels doivent respecter la convention Prometheus.
- Le registre global `REGISTRY` est thread‑safe et peut être partagé.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

__all__ = [
    "REGISTRY",
    "Registry",
    "Counter",
    "Gauge",
    "Histogram",
]
# S6: journal (canonical JSON + hash chain)
try:
    from studio_core.obs.journal import append_event  # type: ignore
except Exception:  # pragma: no cover

    def append_event(*args, **kwargs):
        return ""


def _escape_label_value(value: str) -> str:
    """
    Échapper les caractères spéciaux Prometheus dans les valeurs de label.
    - backslash → \\
    - guillemet → \"
    - saut de ligne → \n
    """
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _normalize_label_tuple(
    label_names: Tuple[str, ...], labels: Optional[Mapping[str, str]]
) -> Tuple[str, ...]:
    """
    Convertit un mapping de labels en tuple ordonné correspondant à `label_names`.
    Vérifie l'exactitude des noms (pas de surplus, pas de manque).
    """
    if not label_names:
        if labels and len(labels) > 0:
            raise ValueError("Cette métrique n'accepte pas de labels.")
        return tuple()

    labels = labels or {}
    if set(labels.keys()) != set(label_names):
        raise ValueError(f"Labels attendus: {label_names}, reçus: {tuple(labels.keys())}")
    return tuple(str(labels[name]) for name in label_names)


def _format_labels(
    label_names: Tuple[str, ...],
    label_values: Tuple[str, ...],
    extra: Optional[Mapping[str, Any]] = None,
) -> str:
    labels = {name: value for name, value in zip(label_names, label_values)}
    if extra:
        labels.update(extra)
    if not labels:
        return ""
    return ",".join(f'{k}="{_escape_label_value(str(v))}"' for k, v in sorted(labels.items()))


class _MetricBase:
    """
    Base commune pour les métriques (non destinée à l'usage direct).
    Gère:
    - nom, aide, type, labels déclarés
    - stockage des échantillons par clé de labels (tuple)
    - verrou pour thread‑safety
    """

    __slots__ = ("name", "help", "type", "label_names", "_samples", "_lock")

    def __init__(self, name: str, help: str, mtype: str, label_names: Iterable[str] = ()):
        self.name: str = name
        self.help: str = help
        self.type: str = mtype  # "counter" | "gauge" | ...
        self.label_names: Tuple[str, ...] = tuple(label_names)
        self._samples: MutableMapping[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def _get(self, labels: Optional[Mapping[str, str]]) -> float:
        key = _normalize_label_tuple(self.label_names, labels)
        with self._lock:
            return self._samples.get(key, 0.0)

    def _set(self, labels: Optional[Mapping[str, str]], value: float) -> None:
        key = _normalize_label_tuple(self.label_names, labels)
        with self._lock:
            self._samples[key] = float(value)

    def _add(self, labels: Optional[Mapping[str, str]], delta: float) -> None:
        key = _normalize_label_tuple(self.label_names, labels)
        with self._lock:
            self._samples[key] = float(self._samples.get(key, 0.0) + delta)

    # Export d'une métrique en texte Prometheus
    def _to_prometheus_lines(self) -> List[str]:
        lines: List[str] = []
        # HELP / TYPE
        lines.append(f"# HELP {self.name} {self.help}")
        lines.append(f"# TYPE {self.name} {self.type}")
        # Samples (ordre stable)
        with self._lock:
            items = sorted(self._samples.items(), key=lambda kv: kv[0])
            for label_values, val in items:
                if self.label_names:
                    labels_repr = ",".join(
                        f'{k}="{_escape_label_value(str(v))}"'
                        for k, v in zip(self.label_names, label_values)
                    )
                    lines.append(f"{self.name}{{{labels_repr}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class Counter(_MetricBase):
    """Compteur monotone (valeur >= 0; inc uniquement)."""

    def __init__(self, name: str, help: str, label_names: Iterable[str] = ()):
        super().__init__(name, help, "counter", label_names)

    def inc(self, labels: Optional[Mapping[str, str]] = None, value: float = 1.0) -> None:
        if value < 0:
            raise ValueError("Un compteur ne peut être décrémenté.")
        self._add(labels, value)


class Gauge(_MetricBase):
    """Jauge (peut monter/descendre)."""

    def __init__(self, name: str, help: str, label_names: Iterable[str] = ()):
        super().__init__(name, help, "gauge", label_names)

    def set(self, labels: Optional[Mapping[str, str]] = None, value: float = 0.0) -> None:
        self._set(labels, value)

    def inc(self, labels: Optional[Mapping[str, str]] = None, value: float = 1.0) -> None:
        self._add(labels, value)

    def dec(self, labels: Optional[Mapping[str, str]] = None, value: float = 1.0) -> None:
        self._add(labels, -value)


class Histogram(_MetricBase):
    """Histogramme simple avec buckets fixes."""

    def __init__(
        self,
        name: str,
        help: str,
        buckets: Iterable[float],
        label_names: Iterable[str] = (),
    ):
        super().__init__(name, help, "histogram", label_names)
        bucket_list = sorted(float(b) for b in buckets)
        if not bucket_list:
            raise ValueError("Au moins un bucket est requis.")
        self.buckets: Tuple[float, ...] = tuple(bucket_list)
        self._bucket_counts: MutableMapping[Tuple[str, ...], List[float]] = {}
        self._sum: MutableMapping[Tuple[str, ...], float] = {}
        self._count: MutableMapping[Tuple[str, ...], float] = {}

    def observe(self, labels: Optional[Mapping[str, str]] = None, value: float = 0.0) -> None:
        key = _normalize_label_tuple(self.label_names, labels)
        v = float(value)
        with self._lock:
            counts = self._bucket_counts.setdefault(
                key, [0.0 for _ in range(len(self.buckets) + 1)]
            )
            for idx, bound in enumerate(self.buckets):
                if v <= bound:
                    counts[idx] += 1.0
            counts[-1] += 1.0  # +Inf bucket
            self._sum[key] = self._sum.get(key, 0.0) + v
            self._count[key] = self._count.get(key, 0.0) + 1.0

    def _to_prometheus_lines(self) -> List[str]:
        lines: List[str] = [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            items = sorted(self._bucket_counts.items(), key=lambda kv: kv[0])
            for label_values, bucket_counts in items:
                cumulative = 0.0
                for idx, bound in enumerate(self.buckets):
                    cumulative += bucket_counts[idx]
                    labels_repr = _format_labels(self.label_names, label_values, {"le": bound})
                    lines.append(f"{self.name}_bucket{{{labels_repr}}} {cumulative}")
                cumulative += bucket_counts[-1]
                labels_repr = _format_labels(self.label_names, label_values, {"le": "+Inf"})
                lines.append(f"{self.name}_bucket{{{labels_repr}}} {cumulative}")

                sum_labels = _format_labels(self.label_names, label_values)
                count = self._count.get(label_values, 0.0)
                total = self._sum.get(label_values, 0.0)
                if sum_labels:
                    lines.append(f"{self.name}_count{{{sum_labels}}} {count}")
                    lines.append(f"{self.name}_sum{{{sum_labels}}} {total}")
                else:
                    lines.append(f"{self.name}_count {count}")
                    lines.append(f"{self.name}_sum {total}")
        return lines


class Registry:
    """
    Registre de métriques thread‑safe.
    - Réutilise la même métrique si redemandée avec type & labels identiques.
    - Export texte Prometheus avec ordre stable.
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, _MetricBase] = {}
        self._lock = threading.Lock()

    # Factory methods
    def counter(self, name: str, help: str, label_names: Iterable[str] = ()) -> Counter:
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                c = Counter(name, help, label_names)
                self._metrics[name] = c
                return c
            if not isinstance(m, Counter):
                raise TypeError(f"La métrique '{name}' existe déjà avec un autre type.")
            if tuple(label_names) != m.label_names:
                raise ValueError(
                    f"Label set différent pour '{name}': déclaré={m.label_names}, demandé={tuple(label_names)}"
                )
            return m  # type: ignore[return-value]

    def gauge(self, name: str, help: str, label_names: Iterable[str] = ()) -> Gauge:
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                g = Gauge(name, help, label_names)
                self._metrics[name] = g
                return g
            if not isinstance(m, Gauge):
                raise TypeError(f"La métrique '{name}' existe déjà avec un autre type.")
            if tuple(label_names) != m.label_names:
                raise ValueError(
                    f"Label set différent pour '{name}': déclaré={m.label_names}, demandé={tuple(label_names)}"
                )
            return m  # type: ignore[return-value]

    def histogram(
        self,
        name: str,
        help: str,
        *,
        buckets: Iterable[float],
        label_names: Iterable[str] = (),
    ) -> Histogram:
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                h = Histogram(name, help, buckets, label_names)
                self._metrics[name] = h
                return h
            if not isinstance(m, Histogram):
                raise TypeError(f"La métrique '{name}' existe déjà avec un autre type.")
            if tuple(label_names) != m.label_names:
                raise ValueError(
                    f"Label set différent pour '{name}': déclaré={m.label_names}, demandé={tuple(label_names)}"
                )
            if tuple(sorted(float(b) for b in buckets)) != m.buckets:
                raise ValueError(
                    f"Buckets différents pour '{name}' : déclaré={m.buckets}, demandé={tuple(sorted(float(b) for b in buckets))}"
                )
            return m  # type: ignore[return-value]

    # Export Prometheus text
    def to_prometheus_text(self) -> str:
        with self._lock:
            metrics = sorted(self._metrics.values(), key=lambda m: m.name)
        lines: List[str] = []
        for m in metrics:
            lines.extend(m._to_prometheus_lines())
        return "\n".join(lines) + ("\n" if lines else "")

    # Utilitaires: récup/présence
    def get(self, name: str) -> Optional[_MetricBase]:
        with self._lock:
            return self._metrics.get(name)

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._metrics.keys())


# Registre global
REGISTRY = Registry()


# ------------------------------------------------------------
# Métriques "conseillées" pour l’app (helpers facultatifs)
# ------------------------------------------------------------


def ensure_default_metrics() -> Dict[str, Counter]:
    """
    Enregistre (sans incrémenter) un set de compteurs conseillés pour l’app.
    Retourne un dict {nom: Counter}.
    """
    defaults = {
        "pp_login_ok": "Logins (clients) réussis",
        "pp_login_fail": "Logins (clients) échoués",
        "pp_totp_ok": "TOTP verifiés (OK)",
        "pp_totp_fail": "TOTP verifiés (KO)",
        "pp_fa_required_hits": "Forward-auth: cas où Turnstile/FA requis",
        "pp_laby_redirects": "Redirections vers l'antichambre (Laby)",
        "pp_webauthn_ok": "WebAuthn verifications (OK)",
        "pp_webauthn_fail": "WebAuthn verifications (KO)",
    }
    out: Dict[str, Counter] = {}
    for k, h in defaults.items():
        out[k] = REGISTRY.counter(k, h)
    return out


# Optionnel: registres par endpoint (log minimaliste)
def record_auth_event(
    endpoint: str,
    decision: str,
    realm: Optional[str] = None,
    risk_score: Optional[float] = None,
    fa_required: Optional[bool] = None,
    pass_required: Optional[bool] = None,
    pass_ok: Optional[bool] = None,
    gate_required: Optional[bool] = None,
    gate_ok: Optional[bool] = None,
    **extras: Any,  # S6: PII-safe only
) -> None:
    """
    Journalisation minimaliste côté métriques:
    - endpoint: "login" | "totp" | "webauthn" | ...
    - decision: "ok" | "fail" | "redirect_laby" | ...
    - realm: "clients" | "dojo" | "laby"
    - risk_score: optionnel (float) — borné [0,1], arrondi 2 déc.
    - fa_required: optionnel (bool)
    - pass_required/pass_ok/gate_required/gate_ok: optionnels (bool)

    Incrémente les compteurs génériques correspondants.
    """
    # Compteurs globaux
    metrics = ensure_default_metrics()

    # S6: clamp/round risk_score for PII-safe logging
    rs_norm: Optional[float] = None
    if risk_score is not None:
        try:
            rs = float(risk_score)
            rs = 0.0 if rs < 0 else (1.0 if rs > 1.0 else rs)
            rs_norm = round(rs, 2)
        except Exception:
            rs_norm = None

    # Dériver et incrémenter selon endpoint/décision
    if endpoint == "login":
        if decision == "ok":
            metrics["pp_login_ok"].inc()
        else:
            metrics["pp_login_fail"].inc()
    elif endpoint == "totp":
        if decision == "ok":
            metrics["pp_totp_ok"].inc()
        else:
            metrics["pp_totp_fail"].inc()
    elif endpoint == "webauthn":
        if decision == "ok":
            metrics["pp_webauthn_ok"].inc()
        else:
            metrics["pp_webauthn_fail"].inc()

    if decision == "redirect_laby":
        metrics["pp_laby_redirects"].inc()
    if fa_required:
        metrics["pp_fa_required_hits"].inc()

    # Exemple: compteur dimensionnel (optionnel)
    # Total des décisions par realm (labels)
    if realm:
        m = REGISTRY.counter(
            "pp_auth_decisions_total",
            "Décisions auth par realm et endpoint",
            label_names=("realm", "endpoint", "decision"),
        )
        m.inc({"realm": realm, "endpoint": endpoint, "decision": decision})

    # S6: append to immutable journal (adapter-first; PII-safe)
    try:
        payload = {
            "source": "auth",
            "endpoint": endpoint,
            "decision": decision,
            "realm": realm,
            "risk_score": rs_norm,
            "fa_required": bool(fa_required) if fa_required is not None else None,
            "pass_required": bool(pass_required) if pass_required is not None else None,
            "pass_ok": bool(pass_ok) if pass_ok is not None else None,
            "gate_required": bool(gate_required) if gate_required is not None else None,
            "gate_ok": bool(gate_ok) if gate_ok is not None else None,
        }
        # Merge extras while filtering to simple JSON scalars
        for k, v in (extras or {}).items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                payload[k] = v
            else:
                payload[k] = str(v)
        append_event(payload)
    except Exception:
        # journaling must never break the app path
        pass


# ------------------------------------------------------------
# Export Prometheus text pour /metrics (ex: via une vue Django)
# ------------------------------------------------------------


def prometheus_text() -> str:
    """
    Retourne l’export en texte (format Prometheus) de toutes les métriques enregistrées.
    """
    return REGISTRY.to_prometheus_text()
