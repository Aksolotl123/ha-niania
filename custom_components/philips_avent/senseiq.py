"""SenseIQ data the monitor pushes over the LAN: breathing and sleep.

The SCD923/SCD973 family computes SenseIQ on the camera and pushes it on two
data points that are not part of the cloud device state, which is why they were
never seen in diagnostics dumps:

- DPS 3, every one to ten seconds while the baby is in the SenseIQ zone:
  ``{"r": "b", "br": 35}``. ``r`` is the reading, ``b`` (still, breathing rate
  measured) or ``m`` (moving, no rate), and ``br`` is breaths per minute.
- DPS 4, about once a minute: the current sleep session as JSON, encoded as hex
  text and then base64. ``st`` is when the baby was put in bed (epoch seconds),
  ``sd`` the session length in seconds, ``css`` the current stage and ``cssd``
  how long it has lasted, ``ssd`` the finished stages in order as single-key
  objects (``{"d": 2014}``). Stages: ``a`` awake, ``l`` light, ``d`` deep; ``o``
  appears too and its meaning is not confirmed yet.

No Home Assistant imports here, so the unit tests can load it directly.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

# Readings stop when the baby leaves the zone, so a reading older than this
# means nobody is in bed. Pushes were observed at most ~11 s apart.
SENSEIQ_FRESH_SECONDS = 60

READING_STILL = "b"
READING_MOVING = "m"

SLEEP_STAGES = {"a": "awake", "l": "light", "d": "deep", "o": "other"}


@dataclass(frozen=True)
class BreathingReading:
    """One DPS 3 push."""

    reading: str
    rate: int | None

    @property
    def in_bed(self) -> bool:
        """Only b and m have been observed; another code may mean nobody is in bed."""
        return self.reading in (READING_STILL, READING_MOVING)

    @property
    def moving(self) -> bool:
        return self.reading == READING_MOVING

    @property
    def breathing_rate(self) -> int | None:
        """Breaths per minute, only while still; the camera sends 0 while moving."""
        if self.reading == READING_STILL and self.rate:
            return self.rate
        return None


def _as_dict(raw: Any) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def parse_breathing(raw: Any) -> BreathingReading | None:
    """Parse a DPS 3 value, or None when it is not a SenseIQ reading."""
    data = _as_dict(raw)
    if not data or not isinstance(data.get("r"), str):
        return None
    rate = data.get("br")
    try:
        rate = int(rate) if rate is not None else None
    except (TypeError, ValueError):
        rate = None
    return BreathingReading(data["r"], rate)


def _decode_sleep_payload(raw: Any) -> dict | None:
    """DPS 4 is base64 of hex of JSON; plain JSON is accepted as well."""
    data = _as_dict(raw)
    if data is not None:
        return data
    if not isinstance(raw, str):
        return None
    try:
        text = base64.b64decode(raw, validate=True).decode("ascii")
        return _as_dict(bytes.fromhex(text).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None


def sleep_stage_name(code: Any) -> str | None:
    if not isinstance(code, str):
        return None
    return SLEEP_STAGES.get(code, code)


def parse_sleep(raw: Any) -> dict | None:
    """Parse a DPS 4 value into plain fields, or None when it cannot be read."""
    data = _decode_sleep_payload(raw)
    if not data:
        return None
    stages = []
    for item in data.get("ssd") or []:
        if isinstance(item, dict) and len(item) == 1:
            code, seconds = next(iter(item.items()))
            if isinstance(seconds, (int, float)):
                stages.append({"stage": sleep_stage_name(code), "seconds": int(seconds)})
    return {
        "in_bed_since": data.get("st") if isinstance(data.get("st"), (int, float)) else None,
        "duration": data.get("sd") if isinstance(data.get("sd"), (int, float)) else None,
        "stage": sleep_stage_name(data.get("css")),
        "stage_duration": data.get("cssd") if isinstance(data.get("cssd"), (int, float)) else None,
        "stages": stages,
    }
