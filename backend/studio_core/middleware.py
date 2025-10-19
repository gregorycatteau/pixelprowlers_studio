from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Ensures a minimal set of security headers are applied when Caddy (reverse proxy)
    is not in front of the Django application. Headers are only set if absent.
    """

    def process_response(self, request, response):
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", "no-referrer")
        response.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=()",
        )
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Embedder-Policy", "same-origin")
        # S7: Ajouter CSP minimal + HSTS si absents (tests et environnements sans proxy terminant TLS)
        response.setdefault(
            "Content-Security-Policy", "default-src 'self'; base-uri 'self'; frame-ancestors 'none'"
        )
        response.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
