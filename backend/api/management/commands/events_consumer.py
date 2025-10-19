# -*- coding: utf-8 -*-
"""
Management command: events_consumer

Consumes JetStream events for the subject "intake.lead.created" and persists a
minimal Lead record into the database.

End-to-end target (Sprint 1):
  n8n (WF-01) → Events Gateway (HMAC) → NATS JetStream → events_consumer → DB

Features:
- Durable JetStream pull consumer (configurable)
- Optional auto-creation of stream (for local/dev) with subject binding
- Safe JSON parsing with poisoning-protection (term invalid messages)
- Persistence using the Lead model (unique on event_id)
- Correlation via request_id (X-Request-ID) propagated end-to-end
- Graceful shutdown on SIGINT/SIGTERM

Environment variables (defaults in brackets):
- NATS_URL                      [nats://nats:4222]
- NATS_USER                     [None]
- NATS_PASS                     [None]
- NATS_STREAM                   [INTAKE]
- NATS_SUBJECT                  [intake.lead.created]
- NATS_DURABLE                  [pxp_leads_durable]
- EVENTS_AUTOCREATE_STREAM      [1]    # if 1, will create stream in local/dev
- EVENTS_PULL_BATCH             [10]   # number of messages to fetch per pull
- EVENTS_PULL_TIMEOUT_SEC       [2]    # per-fetch timeout in seconds

Usage:
    python manage.py events_consumer

Notes:
- In production, prefer managing streams/consumers declaratively with infra-as-code
  rather than auto-creating them at runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from contextlib import suppress
from typing import Any, Dict, Optional

# Model import — expected to exist (added for Sprint 1)
from api.models import Lead  # type: ignore
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

LOGGER = logging.getLogger("events_consumer")
_LOG_LEVEL = os.getenv("EVENTS_CONSUMER_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)


class GracefulExit(SystemExit):
    pass


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "")
    if not val:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Command(BaseCommand):
    help = "Consumes NATS JetStream subject intake.lead.created and persists leads."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Fetch one batch and exit (useful for tests).",
        )

    def handle(self, *args, **options) -> None:
        try:
            asyncio.run(self._async_main(run_once=bool(options.get("once"))))
        except GracefulExit:
            LOGGER.info("Shutting down gracefully.")
        except KeyboardInterrupt:
            LOGGER.info("Interrupted by user, exiting.")
        except Exception as e:
            LOGGER.exception("Unhandled error in events_consumer: %s", e)
            raise SystemExit(1) from e

    async def _async_main(self, run_once: bool = False) -> None:
        # Read configuration
        nats_url = os.getenv("NATS_URL", "nats://nats:4222")
        nats_user = os.getenv("NATS_USER") or None
        nats_pass = os.getenv("NATS_PASS") or None

        stream = os.getenv("NATS_STREAM", "INTAKE")
        subject = os.getenv("NATS_SUBJECT", "intake.lead.created")
        durable = os.getenv("NATS_DURABLE", "pxp_leads_durable")
        autostream = _bool_env("EVENTS_AUTOCREATE_STREAM", True)

        pull_batch = int(os.getenv("EVENTS_PULL_BATCH", "10"))
        pull_timeout = float(os.getenv("EVENTS_PULL_TIMEOUT_SEC", "2"))

        LOGGER.info(
            "Connecting to NATS (url=%s, user=%s, stream=%s, subject=%s, durable=%s, autostream=%s)",
            nats_url,
            "set" if nats_user else "none",
            stream,
            subject,
            durable,
            autostream,
        )

        # Setup graceful shutdown
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _stop(*_):
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, _stop)

        # Connect to NATS + JetStream
        try:
            import nats  # type: ignore
            from nats.errors import TimeoutError as NatsTimeoutError  # type: ignore
        except Exception as e:  # pragma: no cover - import error is fatal in runtime, not test
            LOGGER.error("nats-py is required: pip install nats-py. Error: %s", e)
            raise SystemExit(2) from e

        nc_kwargs: Dict[str, Any] = {"servers": [nats_url]}
        if nats_user or nats_pass:
            nc_kwargs["user"] = nats_user or ""
            nc_kwargs["password"] = nats_pass or ""

        nc = await nats.connect(**nc_kwargs)
        js = nc.jetstream()

        # Optionally create stream (dev convenience)
        if autostream:
            with suppress(Exception):
                info = await js.stream_info(stream)
                LOGGER.info(
                    "Found stream '%s' with %d subjects.", stream, len(info.config.subjects)
                )
            if not await _stream_exists(js, stream):
                LOGGER.info("Creating stream '%s' for subject '%s' (dev-only).", stream, subject)
                await js.add_stream(name=stream, subjects=[subject])

        # Create/attach to durable pull consumer
        sub = None
        try:
            sub = await js.pull_subscribe(subject=subject, durable=durable, stream=stream)
        except Exception as e:
            LOGGER.warning("Consumer missing or incompatible; trying to (re)create: %s", e)
            # Try to (re)create by removing and adding consumer
            with suppress(Exception):
                await js.delete_consumer(stream, durable)
            # Minimal consumer config via add_consumer (API differs per version; fallback to pull_subscribe)
            try:
                sub = await js.pull_subscribe(subject=subject, durable=durable, stream=stream)
            except Exception as ee:
                LOGGER.error("Failed to configure durable consumer: %s", ee)
                await nc.drain()
                await nc.close()
                raise SystemExit(3) from ee

        LOGGER.info("Consumer ready: stream=%s subject=%s durable=%s", stream, subject, durable)

        # Consume loop
        try:
            while not stop_event.is_set():
                try:
                    msgs = await sub.fetch(pull_batch, timeout=pull_timeout)
                except NatsTimeoutError:
                    # No messages in this interval; continue polling
                    msgs = []

                for msg in msgs:
                    try:
                        await self._handle_message(msg)
                    except Exception as handle_err:
                        LOGGER.exception(
                            "Handler error, NAK message to retry later (sid=%s): %s",
                            getattr(msg, "sid", "unknown"),
                            handle_err,
                        )
                        with suppress(Exception):
                            await msg.nak()
                if run_once:
                    break

            LOGGER.info("Stop signal received; draining NATS connection...")
        finally:
            with suppress(Exception):
                await nc.drain()
            with suppress(Exception):
                await nc.close()

    async def _handle_message(self, msg: Any) -> None:
        """
        Parse message and persist a Lead.
        Message body is expected to be a JSON object with at least:
            {
              "subject": "intake.lead.created",
              "data": { "id": "...", "email": "...", "project_name": "...", ... },
              "request_id": "...",
              ...
            }
        """
        raw = bytes(msg.data or b"").decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            LOGGER.error("Invalid JSON; term message (no redelivery). body=%s", raw[:512])
            with suppress(Exception):
                await msg.term()  # best effort; if unsupported, it will raise
            return

        subject = str(payload.get("subject") or "").strip()
        if subject != "intake.lead.created":
            LOGGER.warning("Unexpected subject %r; term to avoid poison loop.", subject)
            with suppress(Exception):
                await msg.term()
            return

        # Extract core fields safely
        data = payload.get("data") or {}
        event_id = str(data.get("id") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        project_name = str(data.get("project_name") or "").strip()
        request_id = str(payload.get("request_id") or "").strip()

        # Basic validation (avoid poisoning the consumer)
        if not event_id or not email or not project_name:
            LOGGER.error(
                "Missing required fields; term message: event_id=%r email=%r project_name=%r",
                event_id,
                email,
                project_name,
            )
            with suppress(Exception):
                await msg.term()
            return

        # Persist with idempotency on event_id
        try:
            with transaction.atomic():
                obj, created = Lead.objects.get_or_create(
                    event_id=event_id,
                    defaults={
                        "email": email,
                        "project_name": project_name,
                        "request_id": request_id,
                        "received_at": timezone.now(),
                        "raw": {
                            # Keep minimal info; avoid PII & secrets
                            "subject": subject,
                            "src": "nats",
                        },
                    },
                )
                if not created:
                    # Optionally update correlation or fields if needed
                    updated = False
                    if request_id and not obj.request_id:
                        obj.request_id = request_id
                        updated = True
                    if updated:
                        obj.save(update_fields=["request_id", "updated_at"])
        except IntegrityError:
            # Unique constraint on event_id — consider as processed
            LOGGER.info("Lead already persisted for event_id=%s", event_id)
        except Exception as db_err:
            LOGGER.exception("DB error while persisting lead (event_id=%s): %s", event_id, db_err)
            # NAK to retry later (e.g., transient DB failures)
            with suppress(Exception):
                await msg.nak()
            return

        # Ack on success
        with suppress(Exception):
            await msg.ack()
        LOGGER.info(
            "Consumed event: subject=%s event_id=%s email=%s request_id=%s",
            subject,
            event_id,
            email,
            request_id or "-",
        )


async def _stream_exists(js: Any, name: str) -> bool:
    with suppress(Exception):
        info = await js.stream_info(name)
        return bool(info)
    return False
