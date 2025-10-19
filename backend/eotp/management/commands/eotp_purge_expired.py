# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from eotp.models import EotpChallenge


class Command(BaseCommand):
    help = "Purge les challenges e-OTP expirés/consommés/locked et exécute VACUUM ANALYZE (PostgreSQL)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compter sans supprimer ni vaccum (affiche seulement les métriques).",
        )
        parser.add_argument(
            "--grace-minutes",
            type=int,
            default=10,
            help="Âge minimal (minutes) des lignes consommées/locked à purger (par défaut 10).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Taille des lots de suppression pour limiter les verrous (défaut 5000).",
        )

    def handle(self, *args, **opts):
        dry_run: bool = bool(opts.get("dry_run"))
        grace_minutes: int = int(opts.get("grace_minutes") or 10)
        batch_size: int = int(opts.get("batch_size") or 5000)

        started = time.time()
        now = timezone.now()
        cutoff = now - timedelta(minutes=grace_minutes)

        self.stdout.write(
            self.style.HTTP_INFO(
                f"[eotp_purge_expired] start dry_run={dry_run} grace={grace_minutes}m batch={batch_size}"
            )
        )

        total_deleted = 0
        total_batches = 0

        # Purge 1: challenges expirés
        q_expired = EotpChallenge.objects.filter(expires_at__lt=now)
        expired_count = q_expired.count()
        self.stdout.write(f"Expired candidates: {expired_count}")

        # Purge 2: challenges consommés/locked plus anciens que la grâce
        q_consumed_locked = EotpChallenge.objects.filter(
            status__in=[EotpChallenge.Status.CONSUMED, EotpChallenge.Status.LOCKED],
            created_at__lt=cutoff,
        )
        consumed_locked_count = q_consumed_locked.count()
        self.stdout.write(
            f"Consumed/Locked (older than {grace_minutes}m) candidates: {consumed_locked_count}"
        )

        if not dry_run:
            # Suppression en lots pour limiter les locks prolongés
            with transaction.atomic():
                # Expired
                total_deleted += self._delete_in_batches(q_expired, batch_size)
                total_batches += (
                    (expired_count + batch_size - 1) // batch_size if expired_count else 0
                )
                # Consumed/Locked
                total_deleted += self._delete_in_batches(q_consumed_locked, batch_size)
                total_batches += (
                    (consumed_locked_count + batch_size - 1) // batch_size
                    if consumed_locked_count
                    else 0
                )

            # VACUUM ANALYZE si on est en PostgreSQL
            if connection.vendor == "postgresql":
                try:
                    with connection.cursor() as cur:
                        cur.execute("VACUUM ANALYZE eotp_challenge;")
                    self.stdout.write(self.style.SUCCESS("VACUUM ANALYZE eotp_challenge executed."))
                except Exception as e:  # pragma: no cover
                    self.stdout.write(
                        self.style.WARNING(f"VACUUM ANALYZE failed (non-blocking): {e}")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"VACUUM ANALYZE skipped for vendor={connection.vendor} (only supported on PostgreSQL)."
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING("Dry-run enabled: no DELETE and no VACUUM executed.")
            )

        duration = time.time() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"[eotp_purge_expired] done batches={total_batches} deleted={total_deleted} duration={duration:.3f}s"
            )
        )

    def _delete_in_batches(self, queryset, batch_size: int) -> int:
        """
        Supprime query par lots de batch_size en se basant sur les PK pour éviter les locks longs.
        """
        deleted = 0
        while True:
            ids = list(
                queryset.values_list("pk", flat=True)[:batch_size]
            )  # slice traduit LIMIT pour PG
            if not ids:
                break
            deleted += EotpChallenge.objects.filter(pk__in=ids).delete()[0]
        return deleted
