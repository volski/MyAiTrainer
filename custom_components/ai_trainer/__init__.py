"""AI Trainer — a Hebrew WhatsApp health coach for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .http import async_register_views
from .panel import async_register_panel, async_unregister_panel
from .runtime import TrainerRuntime
from .services import async_register_services, async_remove_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration namespace."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AI Trainer from a config entry."""
    if entry.entry_id in (hass.data.get(DOMAIN) or {}):
        return True

    runtime = TrainerRuntime(hass, entry)
    await runtime.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_views(hass)
    await async_register_services(hass)
    await async_register_panel(hass)
    _update_whatsapp_issue(hass, runtime)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("AI Trainer %s loaded", runtime.public_settings().get("version"))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    runtime = (hass.data.get(DOMAIN) or {}).pop(entry.entry_id, None)
    if runtime is not None:
        await runtime.async_shutdown()

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)
        await async_unregister_panel(hass)
        async_remove_services(hass)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Apply settings changed through the options flow or panel."""
    runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    if runtime is not None:
        await runtime.async_apply_settings()


def _update_whatsapp_issue(hass: HomeAssistant, runtime: TrainerRuntime) -> None:
    """Create or clear the repair issue about the WhatsApp dependency."""
    if runtime.bridge.available:
        ir.async_delete_issue(hass, DOMAIN, "whatsapp_missing")
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        "whatsapp_missing",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="whatsapp_missing",
    )
