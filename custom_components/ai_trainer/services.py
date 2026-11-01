"""Home Assistant services exposed by AI Trainer."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .runtime import async_get_runtime

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_DAILY_PLAN = "send_daily_plan"
SERVICE_SEND_MESSAGE = "send_message"
SERVICE_ASK = "ask"
SERVICE_RESET_USER = "reset_user"
SERVICE_DELETE_USER = "delete_user"

SERVICE_NAMES = (
    SERVICE_SEND_DAILY_PLAN,
    SERVICE_SEND_MESSAGE,
    SERVICE_ASK,
    SERVICE_RESET_USER,
    SERVICE_DELETE_USER,
)

SEND_PLAN_SCHEMA = vol.Schema(
    {
        vol.Optional("phone"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    }
)

SEND_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("phone"): cv.string,
        vol.Required("message"): cv.string,
    }
)

ASK_SCHEMA = vol.Schema(
    {
        vol.Required("phone"): cv.string,
        vol.Required("prompt"): cv.string,
    }
)

RESET_SCHEMA = vol.Schema({vol.Required("phone"): cv.string})

DELETE_SCHEMA = vol.Schema({vol.Required("phone"): cv.string})


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_DAILY_PLAN):
        return

    async def _runtime():
        runtime = await async_get_runtime(hass)
        if runtime is None:
            raise HomeAssistantError("AI Trainer is not configured.")
        return runtime

    def _users(runtime, phone: str | None) -> list[dict[str, Any]]:
        if phone:
            user = runtime.find_user(phone)
            if user is None:
                raise HomeAssistantError(f"AI Trainer user not found: {phone}")
            return [user]
        return [
            user
            for user in runtime.store.users.values()
            if user.get("status") == "active"
        ]

    async def _handle_send_plan(call: ServiceCall) -> dict[str, Any]:
        runtime = await _runtime()
        users = _users(runtime, call.data.get("phone"))
        force = bool(call.data.get("force", False))
        sent = 0
        for user in users:
            plan = await runtime.agent.async_send_plan_for(
                str(user.get("id")), force=force
            )
            if plan:
                sent += 1
        return {"sent": sent, "users": len(users)}

    async def _handle_send_message(call: ServiceCall) -> dict[str, Any]:
        runtime = await _runtime()
        user = runtime.find_user(str(call.data["phone"]))
        if user is None:
            raise HomeAssistantError("AI Trainer user not found.")
        ok = await runtime.agent.async_send(
            user,
            str(call.data["message"]),
            str(user.get("jid") or ""),
        )
        return {"sent": bool(ok)}

    async def _handle_ask(call: ServiceCall) -> dict[str, Any]:
        runtime = await _runtime()
        user = runtime.find_user(str(call.data["phone"]))
        if user is None:
            raise HomeAssistantError("AI Trainer user not found.")
        await runtime.agent.async_handle_message(
            phone=str(user.get("id")),
            target=str(user.get("jid") or ""),
            name=str(user.get("name") or ""),
            text=str(call.data["prompt"]),
            message_id="service-ask",
        )
        return {"ok": True}

    async def _handle_reset(call: ServiceCall) -> dict[str, Any]:
        runtime = await _runtime()
        ok = await runtime.agent.async_reset_user_for(str(call.data["phone"]))
        if not ok:
            raise HomeAssistantError("AI Trainer user not found.")
        return {"ok": True}

    async def _handle_delete(call: ServiceCall) -> dict[str, Any]:
        runtime = await _runtime()
        ok = await runtime.agent.async_delete_user_for(str(call.data["phone"]))
        if not ok:
            raise HomeAssistantError("AI Trainer user not found.")
        return {"ok": True}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_DAILY_PLAN,
        _handle_send_plan,
        schema=SEND_PLAN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        _handle_send_message,
        schema=SEND_MESSAGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ASK,
        _handle_ask,
        schema=ASK_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_USER,
        _handle_reset,
        schema=RESET_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_USER,
        _handle_delete,
        schema=DELETE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def async_remove_services(hass: HomeAssistant) -> None:
    """Remove services when the last entry is unloaded."""
    for name in SERVICE_NAMES:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
