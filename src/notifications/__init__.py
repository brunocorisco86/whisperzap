"""Módulo de Notificações Externas (ntfy, webhooks)."""

from src.notifications.service import NtfyNotificationService, ntfy_service

__all__ = ["NtfyNotificationService", "ntfy_service"]
