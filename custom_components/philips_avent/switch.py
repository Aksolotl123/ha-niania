"""Switch entities for Philips Avent Baby Monitor."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DPS_AWAKE_SWITCH,
    DPS_CRY_DET_SWITCH,
    DPS_MOTION_SWITCH,
    DPS_NIGHT_LIGHT,
    DPS_PRIVACY_MODE,
    DPS_SENSEIQ_SWITCH,
    DPS_SOUND_SWITCH,
)
from .coordinator import PhilipsAventCoordinator
from .entity import build_device_info

# Created only when the monitor reports the DPS (SenseIQ models).
SENSEIQ_SWITCHES = (
    (DPS_SENSEIQ_SWITCH, "SenseIQ", "mdi:baby-face-outline"),
    (DPS_AWAKE_SWITCH, "Awake Alert", "mdi:baby-face"),
    (DPS_CRY_DET_SWITCH, "Cry Alert", "mdi:emoticon-cry-outline"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for cam_id, coordinator in data["coordinators"].items():
        entities.extend([
            AventSwitch(coordinator, cam_id, DPS_NIGHT_LIGHT, "Night Light", "mdi:lightbulb-night"),
            AventSwitch(coordinator, cam_id, DPS_MOTION_SWITCH, "Motion Alert", "mdi:motion-sensor"),
            AventSwitch(coordinator, cam_id, DPS_SOUND_SWITCH, "Sound Alert", "mdi:ear-hearing"),
            AventEnumSwitch(coordinator, cam_id, DPS_PRIVACY_MODE, "Privacy Mode", "mdi:eye-off"),
        ])
        dps = coordinator.data or {}
        entities.extend(
            AventSwitch(coordinator, cam_id, dps_id, name, icon)
            for dps_id, name, icon in SENSEIQ_SWITCHES
            if dps_id in dps
        )
    async_add_entities(entities)


class AventSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PhilipsAventCoordinator, cam_id: str,
        dps_id: str, name: str, icon: str,
    ):
        super().__init__(coordinator)
        self._cam_id = cam_id
        self._dps_id = dps_id
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{cam_id}_{dps_id}"
        self._attr_device_info = build_device_info(coordinator, cam_id)

    @property
    def is_on(self) -> bool | None:
        dps = self.coordinator.data
        if dps and self._dps_id in dps:
            return bool(dps[self._dps_id])
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.set_dps({self._dps_id: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.set_dps({self._dps_id: False})


class AventEnumSwitch(AventSwitch):
    """Switch for DPS that use "0"/"1" enum instead of bool."""

    @property
    def is_on(self) -> bool | None:
        dps = self.coordinator.data
        if dps and self._dps_id in dps:
            return dps[self._dps_id] == "1"
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.set_dps({self._dps_id: "1"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.set_dps({self._dps_id: "0"})
