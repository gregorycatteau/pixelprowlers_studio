#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_log_chain.py
Adapter-first CLI pour vérifier l'intégrité du journal append-only (Canonical JSON v1 + hash-chaining).

Usage:
  python tools/verify_log_chain.py --file /path/to/auth_journal.log [--deep] [--limit N]
  echo $?
    0 => OK (chaîne valide)
    1 => Erreur de vérification / chaîne corrompue
    2 => Erreur d'exécution (fichier inaccessible, exception, etc.)

Notes:
- Ne loggue aucune PII, affiche un résumé lisible.
- Peut être utilisé en CI/CD ou en runbook.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Import en relative au projet
try:
    from backend.studio_core.obs.journal import verify_chain  # type: ignore
except Exception:
    # Fallback si l'import relatif n'est pas possible (exécution depuis backend/)
    try:
        from studio_core.obs.journal import verify_chain  # type: ignore
    except Exception as e:
        print(f"[verify_log_chain] Import error: {e}", file=sys.stderr)
        sys.exit(2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifier la chaîne de hash du journal append-only."
    )
    parser.add_argument(
        "--file", "-f", required=True, help="Chemin du fichier journal (auth_journal.log)"
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Vérification complète (ne s'arrête pas au premier échec)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limiter la vérification aux N premiers enregistrements",
    )
    args = parser.parse_args()

    log_path = Path(args.file)
    if not log_path.exists():
        print(f"[verify_log_chain] Fichier introuvable: {log_path}", file=sys.stderr)
        return 2

    target_path = log_path
    tmp_to_cleanup = None

    # Option --limit: vérifier uniquement les N premières entrées (approximation)
    if args.limit and int(args.limit) > 0:
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False, prefix="auth_journal_head_", suffix=".log"
            ) as tf:
                tmp_to_cleanup = tf.name
                count = 0
                with log_path.open("r", encoding="utf-8") as src:
                    for line in src:
                        if not line.strip():
                            continue
                        tf.write(line)
                        count += 1
                        if count >= int(args.limit):
                            break
            target_path = Path(tmp_to_cleanup)
        except Exception as e:
            print(f"[verify_log_chain] ERROR — préparation --limit a échoué: {e}", file=sys.stderr)
            return 2

    try:
        ok, checked, err = verify_chain(str(target_path), deep=bool(args.deep))
        if ok:
            suffix = f" (limit={args.limit})" if args.limit else ""
            print(f"[verify_log_chain] OK — intégrité vérifiée ({checked} enregistrements){suffix}")
            rc = 0
        else:
            print(
                f"[verify_log_chain] FAIL — chaîne corrompue après {checked} enregistrements ; cause={err}",
                file=sys.stderr,
            )
            rc = 1
    except Exception as e:
        print(f"[verify_log_chain] ERROR — {e}", file=sys.stderr)
        rc = 2
    finally:
        if tmp_to_cleanup:
            try:
                Path(tmp_to_cleanup).unlink(missing_ok=True)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
