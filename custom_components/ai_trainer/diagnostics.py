"""Diagnostics support for AI Trainer."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    if runtime is None:
        return {"loaded": False}
    users = [
        {
            "id": f"***{str(user.get('phone') or '')[-4:]}",
            "status": user.get("status"),
            "goal": (user.get("profile") or {}).get("goal"),
            "has_plan": bool(user.get("plan")),
            "messages": len(user.get("history") or []),
        }
        for user in runtime.store.users.values()
    ]
    return {
        "loaded": True,
        "version": runtime.public_settings().get("version"),
        "config": async_redact_data(runtime.public_settings(), TO_REDACT),
        "stats": runtime.stats(),
        "users": users,
        "whatsapp_available": runtime.bridge.available,
    }
