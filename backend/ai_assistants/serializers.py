# ai_assistants/serializers.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from rest_framework import serializers

from .models import AgentProfile, Conversation, ConversationMessage, DojoAgent


class AgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = ("name", "description", "model", "temperature", "communication_style", "is_active")


class DojoAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DojoAgent
        fields = ("slug", "title", "description", "capabilities", "is_active")
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    agent = serializers.SlugRelatedField(
        slug_field="slug", queryset=DojoAgent.objects.filter(is_active=True)
    )
    agent_title = serializers.CharField(source="agent.title", read_only=True)
    agent_description = serializers.CharField(source="agent.description", read_only=True)
    creator = serializers.SlugRelatedField(slug_field="username", read_only=True)

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "status",
            "agent",
            "agent_title",
            "agent_description",
            "creator",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "creator",
            "created_at",
            "updated_at",
            "agent_title",
            "agent_description",
        )

    def validate(self, attrs):
        if self.instance and "agent" in attrs:
            raise serializers.ValidationError({"agent": "immutable"})
        return super().validate(attrs)


class ConversationMessageSerializer(serializers.ModelSerializer):
    conversation = serializers.PrimaryKeyRelatedField(queryset=Conversation.objects.all())
    conversation_id = serializers.UUIDField(source="conversation.id", read_only=True)

    class Meta:
        model = ConversationMessage
        fields = (
            "id",
            "conversation",
            "conversation_id",
            "role",
            "content",
            "tokens",
            "created_at",
        )
        read_only_fields = ("id", "conversation_id", "tokens", "created_at")

    def validate_role(self, value: str) -> str:
        # For admin conversations we only authorise the admin role to be "user"
        return ConversationMessage.ROLE_USER

    def create(self, validated_data):
        validated_data["role"] = ConversationMessage.ROLE_USER
        return super().create(validated_data)
