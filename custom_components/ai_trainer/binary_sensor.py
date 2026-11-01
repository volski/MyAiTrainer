"""Binary sensor for WhatsApp availability."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    async_add_entities([WhatsAppSensor(runtime, entry.entry_id)])


class WhatsAppSensor(BinarySensorEntity):
    """Shows whether the WhatsApp send service is available."""

    _attr_should_poll = True
    _attr_has_entity_name = True
    _attr_name = "WhatsApp"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:whatsapp"

    def __init__(self, runtime: TrainerRuntime, entry_id: str) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{entry_id}_whatsapp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="WhatsApp Coach",
            sw_version=VERSION,
        )

    @property
    def is_on(self) -> bool:
        return self.runtime.bridge.available

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "service": self.runtime.bridge.service,
            "account": self.runtime.bridge.account or "default",
        }
