# CHANGELOG-S4 (append-only)
Sprint 4 — Throttling & Résilience (sans Prometheus)
Statut: PROPOSÉ → VALIDÉ (cohérence confirmée) → EN COURS

Date: 2025-10-18
Auteur: Cline

1) Cohérence S4 vs engagements S1–S3 et docs S0
- Alignement:
  - Threat model (§7 “Throttling & anti‑abus”) préconise rate‑limits IP/session/user + backoff exponentiel + Retry‑After générique. Conforme à S4.
  - Observabilité (§07) prévoit compteurs 429, locked, et un futur adapter de métriques. La variante “sans Prometheus” via adapter interne + endpoint JSON debug en DEV/TEST est compatible et non‑rupturiste.
  - S3 UI lit déjà Retry‑After et affiche des messages génériques (non révélants). Les specs E2E “resend cooldown”/“locked” sont vertes et exploitent Retry‑After.
  - S1 services/endpoint e‑OTP (issue/verify/resend) + purge TTL + events auth:eotp_* sont en place; S4 étend sans casser.
- Points d’attention (non bloquants):
  - Redis indispensable pour token bucket/fenêtres fixes précises. Politique de résilience exigée si Redis indisponible (voir §4.4).
  - “Tarpit progressif” côté backend: on applique l’exigence via 429 + Retry‑After progressif (1→2→4→8s, cap 8s). Pas de sleep bloquant dans le worker (évite la saturation). Cela respecte la consigne “Pendant backoff : 429 + Retry‑After = délai restant”.
  - Étendue multi‑tenant: realm scoping prévu via RATELIMIT_REALM_SCOPE (par défaut False). Compatible S0/S1.
Conclusion: Cohérence OK. Lancement S4 validé.

2) Flags/env à introduire (par défaut raisonnable)
- RATELIMIT_ENABLE=True
- RATELIMIT_TTL_VERIFY=60
- RATELIMIT_TTL_RESEND=60
- RATELIMIT_BUCKET_VERIFY=5
- RATELIMIT_BUCKET_RESEND=3
- RATELIMIT_JITTER_PCT=10           # jitter ±10% sur fenêtres fixes si fallback
- BACKOFF_VERIFY_ENABLE=True
- BACKOFF_VERIFY_STEPS="1,2,4,8"    # secondes, cap 8s
- BACKOFF_VERIFY_KEY_TTL=600        # TTL des compteurs d’échecs pour backoff
- RATELIMIT_REALM_SCOPE=False       # True pour préfixer par realm
- REDIS_URL=redis://localhost:6379/0 (prod/stage; dev/test peuvent fallback cache local)

3) Plan d’implémentation (technique)
3.1 Rate‑limit e‑OTP (Redis)
- Module backend/eotp/limits.py:
  - API: check_and_consume(endpoint: Literal["verify","resend"], scopes: dict) -> (allowed: bool, retry_after_s: int)
  - Stratégie:
    - Si Redis disponible: token bucket (Lua simple ou incr/ttl fenêtré amélioré) par scope:
      - ip_prefix (/24, /56), session_key, user_id (si présent)
      - bucket VERIFY=5/min; RESEND=3/min; combine via “worst retry_after” multi‑scope
    - Si Redis non dispo: fallback fixed‑window + jitter ± RATELIMIT_JITTER_PCT (process‑local) + log resilience_warning.
  - Réponse: en cas de dépassement, 429 + header Retry-After (arrondi à 0.5s, ±0.5s max).
- Intégration:
  - eotp/views.py: aux entrées /verify et /resend, avant logique métier → appel check_and_consume; court‑circuit si 429.
  - Journalisation: record_auth_event(“eotp”, “failed”, labels={"rate_limited":true, "retry_after":X}).

3.2 Backoff progressif (verify)
- Stockage Redis clé backoff:{session_key} → niveau d’échec (0..n), TTL BACKOFF_VERIFY_KEY_TTL.
- Évolution: 0→1→2→4→8 (cap 8). Reset sur succès (ok) ou expiration du challenge.
- Comportement:
  - Ne pas bloquer le thread; retourner 429 + Retry‑After = délai restant (soft tarpit).
  - Incrémenter eotp_backoff_applied_total sur application du backoff.

3.3 Abstraction de métriques (sans Prometheus)
- studio_core/metrics_adapter.py:
  - counter_inc(name: str, labels: dict = {})
  - histogram_observe(name: str, value: float, labels: dict = {})
  - Impl par défaut: in‑memory thread‑safe (dicts + locks) + log JSON périodique; future PrometheusAdapter possible sans refactor.
- Points d’incrément:
  - eotp_429_verify_total, eotp_429_resend_total, eotp_backoff_applied_total, eotp_locked_total
  - (option) histogram eotp_issue_to_ok_seconds (issue→ok)

3.4 Endpoint JSON debug (DEV/TEST uniquement)
- GET /debug/eotp-stats → snapshot des compteurs internes (read‑only), jamais en prod (gated via APP_ENV/DEBUG).
- Couverture tests: 200 en DEV/TEST; 404/403 en PROD.

3.5 Logs structurés
- Conserver record_auth_event pour: auth:eotp_issued|resent|ok|failed|expired|locked
- Étendre payload PII‑safe: rate_limited, backoff_applied, retry_after

4) Tests à livrer (verts)
4.1 Pytest backend (eotp/tests/test_throttling.py)
- Rate‑limit IP/session/user → 429 + Retry‑After cohérent (vérifier headers; multi‑scopes “max retry_after”)
- Backoff verify → après 1/2/3/4 échecs: Retry‑After=1/2/4/8; reset après succès/expiration
- /debug/eotp-stats → 200 en DEV/TEST, indispo en PROD
- Résilience: Redis indispo → fallback actif + logs resilience_warning; comportement “fail‑closed maîtrisé”:
  - verify/resend: appliquer limites process‑locales conservatrices (p.ex. VERIFY=3/min, RESEND=2/min), éviter explosion de 200.

4.2 Playwright E2E (complément S3)
- Spam resend → UI désactive btn (Retry‑After) + backend 429
- Bruteforce verify → backend logs montrent backoff_applied; UI inchangée (messages génériques)

5) Outils internes
- tools/test_backoff.sh:
  - Params: --endpoint, --qps, --duration, --ip-profile single|multi, --csv
  - Sorties CSV: taux 200/429, Retry‑After moyen, locked ratio → tools/reports/backoff_test_$(date +%F).csv

6) Sécurité & conformité
- Aucune fuite de secrets/PII (logs/events/JSON debug)
- Messages d’erreur indistinguables (invalid/expired/ratelimit/backoff)
- Retry‑After arrondi ±0.5s (anti‑fingerprinting)
- _peek & /flush désactivés hors TEST (déjà OK)
- CSRF actif partout (déjà OK)

7) Points de décision (arbitrages mineurs)
- Algorithme par défaut: token bucket (si Redis présent); fallback fixed window + jitter (si Redis down temporaire)
- Scope realm:
  - Proposé: RATELIMIT_REALM_SCOPE=False (par défaut). Si True → préfixe “{realm}:” sur toutes les clés pour isolation stricte.
- Politique en cas d’indispo Redis:
  - Fail‑soft contrôlé (limites process‑locales conservatrices + logs de santé) plutôt que fail‑open. Conforme “Sécurité > Ergonomie”.

8) Journal (append)
2025‑10‑18 — Validation de cohérence
- Lecture: todo-S4.md, threat-model.md (§7), observabilité (§07), rapport-final-eotp.md, CHANGELOG‑S3.md.
- Décision: cohérence confirmée; lancement S4 autorisé.
- Plan: voir §3; tests §4; outils §5; sécurité §6.
