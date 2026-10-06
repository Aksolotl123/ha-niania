"""Diagnostics for Philips Avent Baby Monitor."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .redact import mask_id, redact_dps, redact_secrets


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators = data.get("coordinators", {})

    diag: dict[str, Any] = {
        "config_entry": redact_secrets(dict(entry.data)),
        "devices": {},
    }

    for cam_id, coordinator in coordinators.items():
        device_info = None
        if coordinator.device_info:
            # The cloud device record carries its own copy of the DPS (the
            # DPS 212 alarm record with its snapshot URL among them), so that
            # part needs the DPS pass, not only the key-name pass.
            device_info = redact_secrets(
                {k: v for k, v in coordinator.device_info.items() if k != "dps"}
            )
            dps = coordinator.device_info.get("dps")
            if isinstance(dps, dict):
                device_info["dps"] = redact_dps(dps)
        # The device id is an identifier like any other in the dump: keep just
        # enough of it to tell two cameras apart (numbered on the unlikely
        # clash of the last four characters, so no camera is dropped).
        key = mask_id(cam_id)
        if key in diag["devices"]:
            key = f"{key} #{len(diag['devices']) + 1}"
        diag["devices"][key] = {
            "name": coordinator.camera_name,
            "dps": redact_dps(coordinator.data),
            "lan_connected": coordinator.lan_connected,
            "update_interval": str(coordinator.update_interval),
            "rssi": coordinator.rssi,
            "device_info": device_info,
        }

    return diag
