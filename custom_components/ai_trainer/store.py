"""Persistent storage for AI Trainer users and counters.

A single JSON file per config entry holds all users.  Writes are debounced by
Home Assistant's ``Store`` helper and flushed on unload.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, HISTORY_LIMIT, PLAN_HISTORY_LIMIT
from .core.models import ensure_user_shape, new_user, normalize_phone
from .core.text import clean_name

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


class TrainerStore:
    """User store backed by ``homeassistant.helpers.storage.Store``."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.data: dict[str, Any] = {"users": {}, "meta": {"messages": {}}}

    @property
    def users(self) -> dict[str, dict[str, Any]]:
        """Return the mutable users mapping."""
        return self.data.setdefault("users", {})

    async def async_load(self) -> None:
        """Load users from disk."""
        raw = await self._store.async_load()
        if isinstance(raw, dict):
            self.data = {
                "users": raw.get("users") or {},
                "meta": raw.get("meta") or {"messages": {}},
            }
        today = dt_util.now().date().isoformat()
        now_iso = dt_util.now().isoformat()
        for user in self.users.values():
            if isinstance(user, dict):
                ensure_user_shape(user, today, now_iso)
        _LOGGER.debug("Loaded %s AI Trainer users", len(self.users))

    def get_user(self, phone: Any) -> dict[str, Any] | None:
        """Return a user by phone/JID/normalised id."""
        key = normalize_phone(phone)
        if not key:
            return None
        user = self.users.get(key)
        if user is not None:
            return user
        for user in self.users.values():
            if normalize_phone(user.get("phone")) == key:
                return user
        return None

    def create_user(self, phone: Any, jid: str = "", name: str = "") -> dict[str, Any]:
        """Create and persist a new user in onboarding state."""
        normalized = normalize_phone(phone)
        if not normalized:
            raise ValueError("phone is required")
        now = dt_util.now()
        user = new_user(
            normalized,
            jid or f"{normalized}@s.whatsapp.net",
            clean_name(name, fallback=""),
            now.isoformat(),
            now.date().isoformat(),
        )
        self.users[normalized] = user
        self.save()
        return user

    def delete_user(self, phone: Any) -> bool:
        """Delete a user by phone."""
        key = normalize_phone(phone)
        user = self.get_user(key)
        if user is None:
            return False
        self.users.pop(str(user.get("id") or key), None)
        self.save()
        return True

    def touch(self, user: dict[str, Any]) -> None:
        """Update the modification timestamp and schedule a save."""
        user["updated_at"] = dt_util.now().isoformat()
        self.save()

    def add_history(self, user: dict[str, Any], role: str, content: str) -> None:
        """Append a message to the user's conversation history."""
        if role not in {"user", "assistant"}:
            return
        text = str(content or "").strip()
        if not text:
            return
        history = user.setdefault("history", [])
        history.append(
            {
                "role": role,
                "content": text[:4000],
                "ts": dt_util.now().isoformat(),
            }
        )
        del history[:-HISTORY_LIMIT]

    def remember_plan(self, user: dict[str, Any], plan: dict[str, Any]) -> None:
        """Store the day's plan and keep a short history."""
        user["plan"] = plan
        user["last_plan_date"] = plan.get("date")
        history = user.setdefault("plan_history", [])
        history.append(
            {
                "date": plan.get("date"),
                "focus": plan.get("focus"),
                "source": plan.get("source"),
                "text": plan.get("text"),
            }
        )
        del history[:-PLAN_HISTORY_LIMIT]

    def count_message(self) -> None:
        """Increment today's message counter (inbound + outbound)."""
        meta = self.data.setdefault("meta", {})
        messages = meta.setdefault("messages", {})
        today = dt_util.now().date().isoformat()
        messages[today] = int(messages.get(today, 0)) + 1
        cutoff = (dt_util.now().date() - timedelta(days=13)).isoformat()
        for key in list(messages):
            if key < cutoff:
                messages.pop(key, None)
        self.save()

    def messages_today(self) -> int:
        """Return today's message count."""
        today = dt_util.now().date().isoformat()
        return int((self.data.get("meta", {}).get("messages", {})).get(today, 0))

    def save(self) -> None:
        """Schedule a debounced save."""
        self._store.async_delay_save(self._snapshot, 1.0)

    async def async_flush(self) -> None:
        """Persist immediately."""
        await self._store.async_save(self._snapshot())

    def _snapshot(self) -> dict[str, Any]:
        return {"users": self.users, "meta": self.data.get("meta", {})}
