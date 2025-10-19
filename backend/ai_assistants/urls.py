from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .api import ConversationViewSet, DojoAgentViewSet, MessageViewSet

router = DefaultRouter()
router.register("agents", DojoAgentViewSet, basename="dojo-agent")
router.register("conversations", ConversationViewSet, basename="dojo-conversation")
router.register("messages", MessageViewSet, basename="dojo-message")

urlpatterns = [
    # Auth (session)
    path("auth/logout/", views.api_auth_logout, name="api_auth_logout"),
    path("auth/whoami/", views.api_auth_whoami, name="api_auth_whoami"),
    path("auth/nonce/", views.api_auth_nonce, name="api_auth_nonce"),
    path("auth/theme/", views.api_auth_theme, name="api_auth_theme"),
    # Gates
    path("gates/absurdity-check", views.api_gate_absurdity_check, name="api_gate_absurdity_check"),
    path("gates/challenge-init", views.api_gate_challenge_init, name="api_gate_challenge_init"),
    path(
        "gates/challenge-verify", views.api_gate_challenge_verify, name="api_gate_challenge_verify"
    ),
    # Agents
    path("agents/<slug:slug>/ask", views.api_ask_agent, name="api_ask_agent"),
    # Logs
    path("logs", views.api_logs_by_correlation, name="api_logs_by_correlation"),
    path("", include(router.urls)),
]
