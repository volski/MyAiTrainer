"""Daily plan, water and workout scheduling.

A 30-second tick compares the local clock with the configured HH:MM values.
Reminder markers are persisted per user so a Home Assistant restart cannot
send the same reminder twice on the same day.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_TIME,
    CONF_ENABLE_DAILY,
    CONF_ENABLE_WATER,
    CONF_ENABLE_WORKOUT,
    CONF_WATER_TIMES,
    CONF_WORKOUT_TIME,
)
from .core.plan import compose_workout_reminder

if TYPE_CHECKING:
    from .runtime import TrainerRuntime

_LOGGER = logging.getLogger(__name__)

TICK_SECONDS = 30


class TrainerScheduler:
    """Sends proactive messages for all active users."""

    def __init__(self, runtime: TrainerRuntime) -> None:
        self.runtime = runtime
        self._unsub = None

    async def async_start(self) -> None:
        self._unsub = async_track_time_interval(
            self.runtime.hass,
            self._async_tick,
            timedelta(seconds=TICK_SECONDS),
            name="AI Trainer scheduler",
        )

    async def async_stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _async_tick(self, now: datetime) -> None:
        local = dt_util.as_local(now)
        hhmm = local.strftime("%H:%M")
        today = local.date().isoformat()
        settings = self.runtime.settings

        for user in list(self.runtime.store.users.values()):
            if str(user.get("status")) != "active":
                continue
            phone = str(user.get("id") or "")
            if not phone:
                continue
            reminders = user.setdefault(
                "reminders", {"daily": None, "water": None, "workout": None}
            )

            if (
                settings.get(CONF_ENABLE_DAILY, True)
                and hhmm == settings.get(CONF_DAILY_TIME)
                and reminders.get("daily") != today
            ):
                reminders["daily"] = today
                self.runtime.store.touch(user)
                self._spawn(self._async_send_daily(phone))

            water_times = settings.get(CONF_WATER_TIMES) or []
            water_key = f"{today}T{hhmm}"
            if (
                settings.get(CONF_ENABLE_WATER, True)
                and hhmm in water_times
                and reminders.get("water") != water_key
            ):
                reminders["water"] = water_key
                self.runtime.store.touch(user)
                self._spawn(self._async_send_water(phone, hhmm))

            if (
                settings.get(CONF_ENABLE_WORKOUT, True)
                and hhmm == settings.get(CONF_WORKOUT_TIME)
                and reminders.get("workout") != today
            ):
                reminders["workout"] = today
                self.runtime.store.touch(user)
                self._spawn(self._async_send_workout(phone, hhmm))

    def _spawn(self, coro) -> None:
        self.runtime.hass.async_create_task(coro)

    async def _async_send_daily(self, phone: str) -> None:
        async with self.runtime.lock_for(phone):
            user = self.runtime.store.get_user(phone)
            if user is None or user.get("status") != "active":
                return
            try:
                plan = await self.runtime.agent.async_send_plan(
                    user, target=str(user.get("jid") or ""), force=False
                )
                self.runtime.logs.info(
                    "scheduled",
                    f"נשלחה תוכנית יומית ({plan.get('source')})",
                    phone,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("AI Trainer failed to send daily plan")
                self.runtime.logs.error("error", type(err).__name__, phone)

    async def _async_send_water(self, phone: str, time_label: str) -> None:
        async with self.runtime.lock_for(phone):
            user = self.runtime.store.get_user(phone)
            if user is None or user.get("status") != "active":
                return
            try:
                self.runtime.agent._reset_daily_counters(user)
                await self.runtime.agent.async_send_water_reminder(user, time_label)
                self.runtime.logs.info(
                    "scheduled", "נשלחה תזכורת שתייה", phone
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("AI Trainer failed to send water reminder")
                self.runtime.logs.error("error", type(err).__name__, phone)

    async def _async_send_workout(self, phone: str, time_label: str) -> None:
        async with self.runtime.lock_for(phone):
            user = self.runtime.store.get_user(phone)
            if user is None or user.get("status") != "active":
                return
            try:
                plan = await self.runtime.agent.async_build_plan(user, force=False)
                text = compose_workout_reminder(user, plan, time_label)
                await self.runtime.agent.async_send(
                    user, text, str(user.get("jid") or "")
                )
                self.runtime.logs.info(
                    "scheduled", "נשלחה תזכורת אימון", phone
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("AI Trainer failed to send workout reminder")
                self.runtime.logs.error("error", type(err).__name__, phone)
