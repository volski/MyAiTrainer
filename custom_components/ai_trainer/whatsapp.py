"""Bridge to the FaserF/ha-whatsapp integration.

Incoming messages arrive through the ``whatsapp_message_received`` event.
Outgoing messages use the ``whatsapp.send_message`` service, which accepts a
phone number or a full JID as ``target``.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import WHATSAPP_DOMAIN
from .core.text import split_message

_LOGGER = logging.getLogger(__name__)

MAX_CHUNK = 3500


def whatsapp_available(hass: HomeAssistant) -> bool:
    """Return True when the WhatsApp integration registered its service."""
    return hass.services.has_service(WHATSAPP_DOMAIN, "send_message")


def whatsapp_accounts(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return configured WhatsApp accounts for the config flow and panel."""
    accounts: list[dict[str, Any]] = []
    for entry_id, data in (hass.data.get(WHATSAPP_DOMAIN) or {}).items():
        if not isinstance(data, dict) or "client" not in data:
            continue
        entry = hass.config_entries.async_get_entry(entry_id)
        number = ""
        try:
            number = str((data["client"].stats or {}).get("my_number") or "")
        except (AttributeError, TypeError):
            number = ""
        accounts.append(
            {
                "entry_id": entry_id,
                "title": getattr(entry, "title", "") or entry_id,
                "unique_id": getattr(entry, "unique_id", "") or "",
                "number": number.split("@")[0] if number else "",
            }
        )
    accounts.sort(key=lambda item: item.get("title") or "")
    return accounts


class WhatsAppBridge:
    """Send text messages through the WhatsApp integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        account: str = "",
        service: str = "whatsapp.send_message",
    ) -> None:
        self.hass = hass
        self.account = (account or "").strip()
        self.service = (service or "whatsapp.send_message").strip()
        if "." in self.service:
            self.domain, self.service_name = self.service.split(".", 1)
        else:
            self.domain, self.service_name = WHATSAPP_DOMAIN, self.service

    @property
    def available(self) -> bool:
        return self.hass.services.has_service(self.domain, self.service_name)

    async def async_send(self, target: str, message: str) -> bool:
        """Send a WhatsApp message, splitting it when necessary.

        Returns True when every chunk was accepted by the service.
        """
        recipient = str(target or "").strip()
        if not recipient:
            _LOGGER.warning("AI Trainer: cannot send WhatsApp message without target")
            return False
        if not self.available:
            _LOGGER.error(
                "AI Trainer: service %s.%s is not available. Is ha-whatsapp installed?",
                self.domain,
                self.service_name,
            )
            return False

        chunks = split_message(message, MAX_CHUNK)
        if not chunks:
            return False

        for chunk in chunks:
            data: dict[str, Any] = {"target": recipient, "message": chunk}
            if self.account:
                data["account"] = self.account
            try:
                await self.hass.services.async_call(
                    self.domain,
                    self.service_name,
                    data,
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001 - surface provider errors in logs
                _LOGGER.error(
                    "AI Trainer: failed to send WhatsApp message to %s: %s",
                    recipient,
                    type(err).__name__,
                )
                return False
        return True
