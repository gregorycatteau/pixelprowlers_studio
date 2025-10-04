from django.urls import path

from . import views

urlpatterns = [
    # Auth (session)
    path("auth/creds/", views.api_auth_creds, name="api_auth_creds"),
    path("auth/logout/", views.api_auth_logout, name="api_auth_logout"),
    path("auth/whoami/", views.api_auth_whoami, name="api_auth_whoami"),
    # Gates
    path("gates/absurdity-check", views.api_gate_absurdity_check, name="api_gate_absurdity_check"),
    path("gates/challenge-init", views.api_gate_challenge_init, name="api_gate_challenge_init"),
    path(
        "gates/challenge-verify", views.api_gate_challenge_verify, name="api_gate_challenge_verify"
    ),
    # Agents
    path("agents/", views.api_list_agents, name="api_list_agents"),
    path("agents/<slug:slug>/ask", views.api_ask_agent, name="api_ask_agent"),
]
