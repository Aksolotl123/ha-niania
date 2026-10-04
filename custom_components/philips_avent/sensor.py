"""Sensor entities for Philips Avent Baby Monitor."""
from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DPS_TEMPERATURE
from .coordinator import PhilipsAventCoordinator
from .entity import build_device_info
from .senseiq import SLEEP_STAGES


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for cam_id, coordinator in data["coordinators"].items():
        entities.append(AventTemperatureSensor(coordinator, cam_id))
        entities.append(AventWifiSignalSensor(coordinator, cam_id))
        entities.extend([
            AventBreathingRateSensor(coordinator, cam_id),
            AventSleepStageSensor(coordinator, cam_id),
            AventSleepDurationSensor(coordinator, cam_id),
            AventInBedSinceSensor(coordinator, cam_id),
        ])
    async_add_entities(entities)


class AventTemperatureSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "Temperature"

    def __init__(self, coordinator: PhilipsAventCoordinator, cam_id: str):
        super().__init__(coordinator)
        self._cam_id = cam_id
        self._attr_unique_id = f"{cam_id}_temperature"
        self._attr_device_info = build_device_info(coordinator, cam_id)

    @property
    def native_value(self) -> float | None:
        dps = self.coordinator.data
        if dps and DPS_TEMPERATURE in dps:
            return dps[DPS_TEMPERATURE] / 100.0
        return None


class AventWifiSignalSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_has_entity_name = True
    _attr_name = "WiFi Signal"
    _attr_icon = "mdi:wifi"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: PhilipsAventCoordinator, cam_id: str):
        super().__init__(coordinator)
        self._cam_id = cam_id
        self._attr_unique_id = f"{cam_id}_wifi_signal"
        self._attr_device_info = build_device_info(coordinator, cam_id)

    @property
    def native_value(self) -> int | None:
        if hasattr(self.coordinator, "rssi"):
            return self.coordinator.rssi
        return None


class _AventSenseIQSensor(CoordinatorEntity, SensorEntity):
    """Base for the SenseIQ sensors fed by LAN pushes (see senseiq.py)."""

    _attr_has_entity_name = True
    _key = ""

    def __init__(self, coordinator: PhilipsAventCoordinator, cam_id: str):
        super().__init__(coordinator)
        self._cam_id = cam_id
        self._attr_unique_id = f"{cam_id}_{self._key}"
        self._attr_device_info = build_device_info(coordinator, cam_id)

    def _sleep_value(self, field: str):
        sleep = self.coordinator.sleep
        return sleep.get(field) if sleep else None


class AventBreathingRateSensor(_AventSenseIQSensor):
    """Breaths per minute; unknown while the baby moves or is out of bed."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "/min"
    _attr_icon = "mdi:lungs"
    _attr_name = "Breathing Rate"
    _key = "breathing_rate"

    @property
    def native_value(self) -> int | None:
        reading = self.coordinator.breathing
        if reading is None or not self.coordinator.breathing_fresh:
            return None
        return reading.breathing_rate


class AventSleepStageSensor(_AventSenseIQSensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = sorted(set(SLEEP_STAGES.values()))
    _attr_translation_key = "sleep_stage"
    _attr_icon = "mdi:sleep"
    _attr_name = "Sleep Stage"
    _key = "sleep_stage"

    @property
    def native_value(self) -> str | None:
        stage = self._sleep_value("stage")
        return stage if stage in self._attr_options else None

    @property
    def extra_state_attributes(self) -> dict | None:
        sleep = self.coordinator.sleep
        if not sleep:
            return None
        return {"stage_duration_s": sleep.get("stage_duration"), "stages": sleep.get("stages")}


class AventSleepDurationSensor(_AventSenseIQSensor):
    """Time actually asleep (light + deep) in the current session.

    The session length itself also counts awake time and time out of bed, which
    made the value keep growing with an empty crib.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"
    _attr_name = "Sleep Duration"
    _key = "sleep_duration"

    @property
    def native_value(self) -> int | None:
        seconds = self._sleep_value("asleep")
        return round(seconds / 60) if seconds is not None else None

    @property
    def extra_state_attributes(self) -> dict | None:
        sleep = self.coordinator.sleep
        if not sleep:
            return None
        session, in_bed = sleep.get("duration"), sleep.get("in_bed")
        return {
            "session_min": round(session / 60) if session is not None else None,
            "in_bed_min": round(in_bed / 60) if in_bed is not None else None,
        }


class AventInBedSinceSensor(_AventSenseIQSensor):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bed-clock"
    _attr_name = "In Bed Since"
    _key = "in_bed_since"

    @property
    def native_value(self) -> datetime | None:
        stamp = self._sleep_value("in_bed_since")
        if not stamp or self._sleep_value("stage") == "out":
            return None
        return datetime.fromtimestamp(stamp, tz=UTC)
