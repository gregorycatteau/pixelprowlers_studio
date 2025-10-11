from __future__ import annotations

import time

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from studio_core.metrics import REGISTRY

from .models import Conversation, ConversationAuditLog, ConversationMessage, DojoAgent
from .permissions import RequireSignedNonce
from .security import issue_chained_nonce
from .serializers import ConversationMessageSerializer, ConversationSerializer, DojoAgentSerializer

METRIC_CONVERSATIONS_CREATED = REGISTRY.counter(
    "dojo_conversations_created_total",
    "Number of Dojo conversations created.",
    label_names=("agent", "status"),
)
METRIC_MESSAGES_CREATED = REGISTRY.counter(
    "dojo_messages_created_total",
    "Number of Dojo conversation messages created.",
    label_names=("agent", "role"),
)
METRIC_REQUEST_LATENCY_MS = REGISTRY.histogram(
    "dojo_request_latency_ms",
    "Latency for Dojo conversation/message endpoints (milliseconds).",
    label_names=("endpoint", "method"),
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)


def _observe_latency(endpoint: str, method: str, duration_ms: float) -> None:
    try:
        METRIC_REQUEST_LATENCY_MS.observe(
            {"endpoint": endpoint, "method": method},
            max(duration_ms, 0.0),
        )
    except Exception:
        # Metrics should never break request flow.
        pass


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.META.get("REMOTE_ADDR")


def audit_log(request, action: str, obj, extra: dict | None = None) -> None:
    ConversationAuditLog.objects.create(
        actor=request.user if getattr(request.user, "is_authenticated", False) else None,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(getattr(obj, "pk", "")),
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:512],
        request_id=getattr(request, "request_id", ""),
        extra=extra or {},
    )


CSRF_HEADER_PARAM = OpenApiParameter(
    name="X-CSRFToken",
    location=OpenApiParameter.HEADER,
    required=True,
    type=OpenApiTypes.STR,
    description="CSRF token issued via /api/auth/csrf/ (session cookie).",
)
NONCE_HEADER_PARAM = OpenApiParameter(
    name="X-Request-Nonce",
    location=OpenApiParameter.HEADER,
    required=True,
    type=OpenApiTypes.STR,
    description="Signed nonce obtained from /api/auth/nonce/. TTL=60s, single use.",
)
MESSAGES_CONVERSATION_PARAM = OpenApiParameter(
    name="conversation",
    location=OpenApiParameter.QUERY,
    required=True,
    type=OpenApiTypes.UUID,
    description="Conversation UUID to filter the message history.",
)


def _attach_nonce(response: Response | None, user_id: int | None) -> Response | None:
    if isinstance(response, Response):
        issue_chained_nonce(response, user_id=user_id)
    return response


@extend_schema_view(
    list=extend_schema(
        tags=["Agents"],
        summary="List active Dojo agents",
        description="Returns the catalogue of agents available to superusers.",
    ),
    retrieve=extend_schema(
        tags=["Agents"],
        summary="Retrieve a Dojo agent",
        description="Fetch details for a specific Dojo agent.",
    ),
)
class DojoAgentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DojoAgent.objects.filter(is_active=True).order_by("title")
    serializer_class = DojoAgentSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    lookup_field = "slug"
    pagination_class = None


class ConversationPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"


class MessagePagination(PageNumberPagination):
    page_size = 50
    max_page_size = 200
    page_size_query_param = "page_size"


class ConversationCreateRate(ScopedRateThrottle):
    scope = "conversations_create"


class MessageCreateRate(ScopedRateThrottle):
    scope = "messages_create"


@extend_schema_view(
    list=extend_schema(
        tags=["Conversations"],
        summary="List conversations",
        description="Paginated list (20 per page) scoped to the authenticated creator.",
    ),
    retrieve=extend_schema(
        tags=["Conversations"],
        summary="Retrieve a conversation",
    ),
    create=extend_schema(
        tags=["Conversations"],
        summary="Create a new conversation",
        parameters=[CSRF_HEADER_PARAM, NONCE_HEADER_PARAM],
        responses={201: ConversationSerializer},
    ),
    partial_update=extend_schema(
        tags=["Conversations"],
        summary="Update conversation title or status",
        parameters=[CSRF_HEADER_PARAM, NONCE_HEADER_PARAM],
    ),
    destroy=extend_schema(
        tags=["Conversations"],
        summary="Archive a conversation",
        parameters=[CSRF_HEADER_PARAM, NONCE_HEADER_PARAM],
        responses={204: OpenApiResponse(description="Conversation archived.")},
    ),
)
class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser, RequireSignedNonce]
    lookup_field = "id"
    pagination_class = ConversationPagination

    def get_queryset(self):
        return (
            Conversation.objects.select_related("agent")
            .filter(creator=self.request.user)
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        start = time.perf_counter()
        response = super().create(request, *args, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000.0
        _observe_latency("conversations", request.method, duration_ms)
        user_id = getattr(request.user, "pk", None)
        return _attach_nonce(response, user_id=user_id)

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "create":
            throttles.append(ConversationCreateRate())
        return throttles

    def perform_create(self, serializer):
        agent = serializer.validated_data.get("agent")
        if not agent or not agent.is_active:
            raise ValidationError({"agent": "agent_inactive"})

        with transaction.atomic():
            conversation = serializer.save(creator=self.request.user)
            audit_log(self.request, "conversation_created", conversation, {"agent": agent.slug})
            agent_slug = getattr(agent, "slug", "") or "unknown"
            try:
                METRIC_CONVERSATIONS_CREATED.inc(
                    {"agent": agent_slug, "status": conversation.status}
                )
            except Exception:
                pass
        return conversation

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        start = time.perf_counter()
        response = super().update(request, *args, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000.0
        _observe_latency("conversations", request.method, duration_ms)
        return _attach_nonce(response, user_id=getattr(request.user, "pk", None))

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.creator_id != self.request.user.id:
            raise PermissionDenied("forbidden")

        status_value = serializer.validated_data.get("status")
        if status_value and status_value not in dict(Conversation.STATUS_CHOICES):
            raise ValidationError({"status": "invalid_status"})

        with transaction.atomic():
            conversation = serializer.save()
            audit_log(
                self.request,
                "conversation_updated",
                conversation,
                {"status": conversation.status, "title": conversation.title},
            )
        return conversation

    def destroy(self, request, *args, **kwargs):
        start = time.perf_counter()
        conversation = self.get_object()
        if conversation.status == Conversation.STATUS_ARCHIVED:
            response = Response(status=status.HTTP_204_NO_CONTENT)
            duration_ms = (time.perf_counter() - start) * 1000.0
            _observe_latency("conversations", request.method, duration_ms)
            return _attach_nonce(response, user_id=getattr(request.user, "pk", None))

        conversation.status = Conversation.STATUS_ARCHIVED
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["status", "updated_at"])
        audit_log(request, "conversation_archived", conversation)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        duration_ms = (time.perf_counter() - start) * 1000.0
        _observe_latency("conversations", request.method, duration_ms)
        return _attach_nonce(response, user_id=getattr(request.user, "pk", None))


@extend_schema_view(
    list=extend_schema(
        tags=["Messages"],
        summary="List messages",
        description="Returns messages ordered chronologically for a conversation.",
        parameters=[MESSAGES_CONVERSATION_PARAM],
    ),
    create=extend_schema(
        tags=["Messages"],
        summary="Send a new user message",
        parameters=[CSRF_HEADER_PARAM, NONCE_HEADER_PARAM],
        responses={201: ConversationMessageSerializer},
    ),
)
class MessageViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ConversationMessageSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser, RequireSignedNonce]
    pagination_class = MessagePagination

    def get_queryset(self):
        qs = ConversationMessage.objects.select_related("conversation", "conversation__agent")
        conversation_id = self.request.query_params.get("conversation")
        if not conversation_id:
            return qs.none()
        try:
            conversation = Conversation.objects.select_related("agent").get(
                pk=conversation_id, creator=self.request.user
            )
        except Conversation.DoesNotExist as exc:
            raise PermissionDenied("forbidden") from exc
        except ValueError as exc:
            raise ValidationError({"conversation": "invalid"}) from exc
        return qs.filter(conversation=conversation).order_by("created_at")

    def list(self, request, *args, **kwargs):
        if "conversation" not in request.query_params:
            raise ValidationError({"conversation": "required"})
        return super().list(request, *args, **kwargs)

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "create":
            throttles.append(MessageCreateRate())
        return throttles

    def perform_create(self, serializer):
        conversation: Conversation = serializer.validated_data.get("conversation")
        if conversation.creator_id != self.request.user.id:
            raise PermissionDenied("forbidden")
        if conversation.status == Conversation.STATUS_ARCHIVED:
            raise ValidationError({"conversation": "conversation_archived"})

        with transaction.atomic():
            message = serializer.save()
            audit_log(
                self.request,
                "message_created",
                conversation,
                {"message_id": str(message.id)},
            )
            agent_slug = getattr(getattr(conversation, "agent", None), "slug", "") or "unknown"
            try:
                METRIC_MESSAGES_CREATED.inc({"agent": agent_slug, "role": message.role})
            except Exception:
                pass
        return message

    def create(self, request, *args, **kwargs):
        start = time.perf_counter()
        response = super().create(request, *args, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000.0
        _observe_latency("messages", request.method, duration_ms)
        return _attach_nonce(response, user_id=getattr(request.user, "pk", None))
