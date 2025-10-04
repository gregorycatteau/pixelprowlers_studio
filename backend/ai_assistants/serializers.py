# ai_assistants/serializers.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from rest_framework import serializers

from .models import AgentProfile


class AgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = ("name", "description", "model", "temperature", "communication_style", "is_active")
