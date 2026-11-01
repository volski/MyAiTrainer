"""Register the sidebar panel and its static assets."""

from __future__ import annotations

import inspect
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_JS,
    PANEL_TITLE,
    PANEL_URL,
    STATIC_URL,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

_STATIC_KEY = f"{DOMAIN}_static_registered"


async def async_register_static(hass: HomeAssistant) -> None:
    """Serve the panel JavaScript from the integration directory."""
    if hass.data.get(_STATIC_KEY):
        return
    folder = Path(__file__).parent / "frontend"
    if not folder.is_dir():
        _LOGGER.error("AI Trainer frontend directory is missing: %s", folder)
        return
    config = StaticPathConfig(STATIC_URL, str(folder), False)
    try:
        await hass.http.async_register_static_paths([config])
    except AttributeError:
        # Home Assistant < 2024.7
        hass.http.register_static_path(STATIC_URL, str(folder), False)  # type: ignore[attr-defined]
    hass.data[_STATIC_KEY] = True


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the AI Trainer custom panel in the sidebar."""
    await async_register_static(hass)
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"{STATIC_URL}/{PANEL_JS}?v={VERSION}",
            config={},
            require_admin=True,
            embed_iframe=False,
        )
    except ValueError:
        # Already registered (for example after a quick reload).
        _LOGGER.debug("AI Trainer panel already registered")


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel when the last entry is deleted."""
    panels = hass.data.get("frontend_panels") or {}
    if PANEL_URL not in panels:
        return
    try:
        result = frontend.async_remove_panel(hass, PANEL_URL)
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 - panel removal must never block unload
        _LOGGER.debug("Could not remove AI Trainer panel", exc_info=True)
