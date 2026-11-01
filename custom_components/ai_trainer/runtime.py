"""Integration runtime: configuration, provider, storage and scheduling."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .agent import TrainerAgent
from .ai import AIError, create_provider, provider_catalogue
from .const import (
    CONF_API_KEY,
    CONF_COACH_NAME,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_WHATSAPP_ACCOUNT,
    CONF_WHATSAPP_SERVICE,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    VERSION,
    merged_settings,
    provider_meta,
)
from .core.metrics import targets_for
from .core.plan import plan_public_view
from .logs import EventLog
from .scheduler import TrainerScheduler
from .store import TrainerStore
from .whatsapp import WhatsAppBridge, whatsapp_accounts, whatsapp_available

_LOGGER = logging.getLogger(__name__)


class TrainerRuntime:
    """One running AI Trainer instance (one config entry)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = TrainerStore(hass, entry.entry_id)
        self.logs = EventLog()
        self.settings: dict[str, Any] = merged_settings(entry.data, entry.options)
        self._session: aiohttp.ClientSession | None = None
        self.provider = None
        self.bridge = WhatsAppBridge(hass)
        self.agent = TrainerAgent(self)
        self.scheduler = TrainerScheduler(self)
        self._unsub = None
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Load storage, build helper objects and start listening."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120)
        )
        await self.store.async_load()
        self._apply_settings()
        self._unsub = self.hass.bus.async_listen(
            EVENT_MESSAGE_RECEIVED, self._handle_whatsapp_event
        )
        await self.scheduler.async_start()
        self.logs.info(
            "startup",
            f"AI Trainer {VERSION} פעיל · ספק: {provider_meta(self.settings.get(CONF_PROVIDER)).get('label')}",
        )
        if not self.bridge.available:
            self.logs.warning(
                "whatsapp_missing",
                "שירות whatsapp.send_message לא נמצא — התקינו את ha-whatsapp",
            )

    async def async_shutdown(self) -> None:
        """Stop listeners, flush state and close the HTTP session."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await self.scheduler.async_stop()
        await self.store.async_flush()
        if self._session is not None:
            await self._session.close()
            self._session = None
        self.logs.info("shutdown", "AI Trainer נעצר")

    def _apply_settings(self) -> None:
        """Rebuild the provider and bridge from the current entry options."""
        self.settings = merged_settings(self.entry.data, self.entry.options)
        if self._session is not None:
            self.provider = create_provider(self.settings, self._session)
        self.bridge = WhatsAppBridge(
            self.hass,
            account=str(self.settings.get(CONF_WHATSAPP_ACCOUNT) or ""),
            service=str(self.settings.get(CONF_WHATSAPP_SERVICE) or "whatsapp.send_message"),
        )

    async def async_apply_settings(self) -> None:
        """Apply updated options without reloading the entry."""
        self._apply_settings()
        self.logs.info("settings", "ההגדרות עודכנו")
        await self.store.async_flush()

    def lock_for(self, key: str) -> asyncio.Lock:
        """Return a per-user lock to serialise conversation work."""
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    # ------------------------------------------------------------------
    # WhatsApp events
    # ------------------------------------------------------------------
    def _handle_whatsapp_event(self, event) -> None:
        """Forward a WhatsApp event to the agent on the event loop."""
        data = dict(event.data or {})
        self.logs.info("whatsapp_raw", f"raw event keys: {list(data.keys())}")
        account = str(self.settings.get(CONF_WHATSAPP_ACCOUNT) or "").strip()
        if account:
            event_entry = str(data.get("entry_id") or "")
            if event_entry and event_entry != account:
                matches = False
                known = False
                for info in whatsapp_accounts(self.hass):
                    if account in {
                        info.get("entry_id"),
                        info.get("title"),
                        info.get("unique_id"),
                        info.get("number"),
                    }:
                        known = True
                        matches = info.get("entry_id") == event_entry
                        break
                if known and not matches:
                    self.logs.warning(
                        "account_mismatch",
                        f"הודעה מ-account {event_entry} (מוגדר {account}) — מעובד בכל זאת",
                    )
                if not known:
                    self.logs.warning(
                        "config",
                        f"WhatsApp account '{account}' לא זוהה — מעובד בכל זאת",
                    )
        self.hass.async_create_task(self.agent.async_handle_event(data))

    # ------------------------------------------------------------------
    # Panel data
    # ------------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        """Return aggregated counters for the dashboard."""
        users = list(self.store.users.values())
        active = len([u for u in users if u.get("status") == "active"])
        paused = len([u for u in users if u.get("status") == "paused"])
        onboarding = len([u for u in users if u.get("status") == "onboarding"])
        last_plan = max(
            (str(u.get("last_plan_date") or "") for u in users),
            default="",
        )
        return {
            "users": len(users),
            "active": active,
            "paused": paused,
            "onboarding": onboarding,
            "messages_today": self.store.messages_today(),
            "last_plan_date": last_plan or None,
            "provider_ready": bool(self.provider and self.provider.ready),
            "provider": str(self.settings.get(CONF_PROVIDER) or ""),
            "model": str(self.provider.model if self.provider else ""),
            "whatsapp_available": self.bridge.available,
        }

    def public_settings(self) -> dict[str, Any]:
        """Return settings with secrets redacted for the panel."""
        public = dict(self.settings)
        key = str(public.pop(CONF_API_KEY, "") or "")
        public["api_key_set"] = bool(key)
        public["api_key_hint"] = f"••••{key[-4:]}" if len(key) >= 4 else ("••••" if key else "")
        meta = provider_meta(self.settings.get(CONF_PROVIDER))
        public["provider_label"] = meta.get("label", "")
        public["effective_model"] = str(
            self.settings.get(CONF_MODEL) or meta.get("default_model") or ""
        )
        public["provider_ready"] = bool(self.provider and self.provider.ready)
        public["version"] = VERSION
        return public

    def config_payload(self) -> dict[str, Any]:
        """Return the whole configuration payload for the panel."""
        return {
            "version": VERSION,
            "settings": self.public_settings(),
            "providers": provider_catalogue(),
            "whatsapp": {
                "available": whatsapp_available(self.hass),
                "service_available": self.bridge.available,
                "accounts": whatsapp_accounts(self.hass),
            },
            "stats": self.stats(),
            "timezone": str(dt_util.DEFAULT_TIME_ZONE),
        }

    def user_summary(self, user: dict[str, Any]) -> dict[str, Any]:
        """Return a compact user record for tables."""
        profile = user.get("profile") or {}
        stats = user.get("stats") or {}
        targets = targets_for(profile)
        water_done = int(stats.get("water_ml_today") or 0)
        water_target = int(targets.get("water_ml") or 0)
        today = dt_util.now().date()
        week_start = (today - timedelta(days=6)).isoformat()
        week_workouts = len(
            [day for day in (stats.get("workouts") or []) if str(day) >= week_start]
        )
        return {
            "id": user.get("id"),
            "phone": user.get("phone"),
            "name": user.get("name") or "",
            "status": user.get("status") or "unknown",
            "onboarding_step": user.get("onboarding_step"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "goal": profile.get("goal"),
            "goal_label": targets.get("goal_label"),
            "goal_text": profile.get("goal_text") or "",
            "weight_kg": profile.get("weight_kg"),
            "height_cm": profile.get("height_cm"),
            "bmi": targets.get("bmi"),
            "bmi_category": targets.get("bmi_category"),
            "bmi_color": targets.get("bmi_color"),
            "calories": targets.get("calories"),
            "protein_g": targets.get("protein_g"),
            "water_l": targets.get("water_l"),
            "water_done_ml": water_done,
            "water_target_ml": water_target,
            "water_percent": (
                int(round(water_done / water_target * 100)) if water_target else 0
            ),
            "workouts_week": week_workouts,
            "weekly_workouts": targets.get("weekly_workouts"),
            "streak": self.agent._streak(user),
            "last_plan_date": user.get("last_plan_date"),
            "last_checkin": stats.get("last_checkin"),
            "messages_today": int(stats.get("messages_today") or 0),
        }

    def user_detail(self, user: dict[str, Any]) -> dict[str, Any]:
        """Return a user record including profile, plan and history."""
        detail = self.user_summary(user)
        detail.update(
            {
                "profile": dict(user.get("profile") or {}),
                "notes": user.get("notes") or "",
                "plan": plan_public_view(user.get("plan")),
                "plan_text": str((user.get("plan") or {}).get("text") or ""),
                "plan_history": list(user.get("plan_history") or [])[-5:],
                "history": list(user.get("history") or [])[-40:],
                "stats": dict(user.get("stats") or {}),
                "reminders": dict(user.get("reminders") or {}),
            }
        )
        return detail

    # ------------------------------------------------------------------
    # Tests / helpers
    # ------------------------------------------------------------------
    async def async_test_provider(self) -> dict[str, Any]:
        """Run a tiny completion to validate provider settings."""
        if not self.provider or not self.provider.ready:
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מפתח או מודל).")
        started = time.monotonic()
        text = await self.provider.test()
        elapsed = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "message": text[:200],
            "latency_ms": elapsed,
            "provider": self.settings.get(CONF_PROVIDER),
            "model": self.provider.model,
        }

    async def async_test_whatsapp(self, phone: str) -> dict[str, Any]:
        """Send a test message through WhatsApp."""
        coach = str(self.settings.get(CONF_COACH_NAME) or "המאמן")
        ok = await self.bridge.async_send(
            phone, f"🧪 בדיקה מ־AI Trainer\nשלום! אני {coach}, והחיבור עובד."
        )
        return {"ok": ok, "phone": phone}

    def find_user(self, identifier: str) -> dict[str, Any] | None:
        """Resolve a panel identifier (phone or internal id)."""
        user = self.store.get_user(identifier)
        if user is not None:
            return user
        for candidate in self.store.users.values():
            if str(candidate.get("id")) == str(identifier):
                return candidate
        return None


async def async_get_runtime(
    hass: HomeAssistant, entry_id: str | None = None
) -> TrainerRuntime | None:
    """Return a runtime, preferring the requested entry."""
    entries: dict[str, TrainerRuntime] = hass.data.get(DOMAIN, {})
    if entry_id and entry_id in entries:
        return entries[entry_id]
    if len(entries) == 1:
        return next(iter(entries.values()))
    return None
