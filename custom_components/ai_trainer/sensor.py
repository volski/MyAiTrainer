"""Diagnostic sensors for AI Trainer."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME, VERSION
from .runtime import TrainerRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: TrainerRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            UsersSensor(runtime, entry.entry_id),
            ActiveUsersSensor(runtime, entry.entry_id),
            MessagesTodaySensor(runtime, entry.entry_id),
        ]
    )


class BaseSensor(SensorEntity):
    """Base entity for AI Trainer counters."""

    _attr_should_poll = True
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime: TrainerRuntime, entry_id: str) -> None:
        self.runtime = runtime
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="WhatsApp Coach",
            sw_version=VERSION,
        )
        self._attr_unique_id = f"{entry_id}_{self.__class__.__name__.lower()}"


class UsersSensor(BaseSensor):
    """Total number of registered users."""

    _attr_name = "Users"
    _attr_icon = "mdi:account-group"

    @property
    def native_value(self) -> int:
        return int(self.runtime.stats()["users"])


class ActiveUsersSensor(BaseSensor):
    """Number of active users."""

    _attr_name = "Active users"
    _attr_icon = "mdi:account-check"

    @property
    def native_value(self) -> int:
        return int(self.runtime.stats()["active"])


class MessagesTodaySensor(BaseSensor):
    """Messages exchanged today."""

    _attr_name = "Messages today"
    _attr_icon = "mdi:message-text-clock"

    @property
    def native_value(self) -> int:
        return int(self.runtime.stats()["messages_today"])
