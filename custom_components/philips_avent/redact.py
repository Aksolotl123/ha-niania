"""Secret redaction shared by the debug log and the diagnostics dump.

docs/reporting-issues.md tells users their password, session token, email and
device keys are stripped before anything leaves their machine, and the issue
template repeats it while asking for the debug log. That promise has to hold
for both outputs, so both go through this module.

Tuya discovery responses are the hard case: ``localKey`` — which is enough to
control the camera over the LAN on its own — sits inside lists of device dicts,
and household coordinates ride along in the home objects. Redaction therefore
walks lists as well as dicts.

Key matching is deliberately loose. Comparing the exact lower-cased name let
``accessToken``, ``localKeyV2``, ``p2pKey``, ``mqttPassword`` or ``clientSecret``
through in plain text, so names are normalised (lower case, no ``_``/``-``)
and anything that merely *contains* a secret-looking word is redacted too,
with a short allowlist for harmless words that happen to contain ``key``.
Device and household identifiers (device id, IP, MAC, serial, home id) are
redacted as well: they are not credentials, but a diagnostics file attached to
a public issue should not tie a monitor to its owner.

DPS values need their own pass (``redact_dps``): DPS 212 is a base64 JSON alarm
record whose ``files`` entry points at the alarm snapshot in the Tuya cloud.

No Home Assistant or aiohttp imports here, so the unit tests can load it
directly.
"""
from __future__ import annotations

import base64
import binascii
import json

REDACTED = "**REDACTED**"


def normalize_key(key: object) -> str:
    """Lower-case a key and drop ``_``, ``-`` and spaces, for matching."""
    return str(key).lower().replace("_", "").replace("-", "").replace(" ", "")


# Normalised (see ``normalize_key``); a key is redacted when its normalised
# form is in this set.
SECRET_KEYS = frozenset({
    # Session and account
    "sid", "ecode", "uid", "partner", "partneridentity",
    "email", "username", "mobile", "phone", "sessionid", "cookie",
    # Device
    "localkey", "psk", "devkey",
    # Tuya app keys, entered in the config flow
    "appkey", "signingkey", "chkey", "clientid", "ttid",
    # Location
    "lat", "lon", "lng", "latitude", "longitude",
    # Alarm snapshot references in the cloud (DPS 212)
    "files",
})

# Identifiers that tie a device or a household to its owner. ``id`` is the
# camera's device id in the stored config entry (``cameras: [{"id": ...}]``).
IDENTIFIER_KEYS = frozenset({
    "id", "devid", "deviceid", "cameraid", "gwid", "gatewayid", "nodeid",
    "meshid", "uuid", "gid", "homeid", "ownerid", "owneruid",
    "ip", "lanip", "localip", "wanip", "publicip", "ipaddress",
    "mac", "macaddress", "bssid", "ssid",
    "sn", "serial", "serialno", "serialnumber",
})

# A key whose normalised form contains any of these is redacted.
SECRET_SUBSTRINGS = (
    "token", "secret", "password", "passwd", "pwd", "credential", "key",
)

# Harmless keys that contain one of the substrings above. ``productKey`` is the
# Tuya product identifier, the same kind of value as ``productId``.
ALLOWED_KEYS = frozenset({
    "productkey", "keyboard", "keyword", "keywords", "keyframe",
    "monkey", "donkey", "turkey", "hockey", "jockey", "whiskey",
})


def is_secret_key(key: object) -> bool:
    """Whether a value stored under ``key`` must not leave the machine."""
    norm = normalize_key(key)
    if norm in SECRET_KEYS or norm in IDENTIFIER_KEYS:
        return True
    if norm in ALLOWED_KEYS:
        return False
    return any(part in norm for part in SECRET_SUBSTRINGS)


def redact_secrets(value):
    """Return ``value`` with every secret-looking key replaced by a marker.

    Walks dicts, lists and tuples; anything else is returned as-is. The input
    is never mutated. Sequences come back as lists.
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if is_secret_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    return value


def mask_id(value: object) -> str:
    """A device or home id cut down to its last four characters, for log lines.

    Enough to tell two devices apart in a log, not enough to look one up.
    """
    text = "" if value is None else str(value)
    if len(text) <= 4:
        return "***"
    return "***" + text[-4:]


# DPS 212, the base64 JSON alarm record (see events.py). Duplicated from
# const.py so this module stays importable without the package.
DPS_ALARM_RECORD = "212"


def _decode_json_value(raw: str) -> dict | list | None:
    """Decode a DPS string carrying JSON, plain or base64-encoded."""
    text = raw.strip()
    if not text:
        return None
    if not text.startswith(("{", "[")):
        try:
            text = base64.b64decode(text, validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return decoded if isinstance(decoded, (dict, list)) else None


def _scrub_urls(value):
    """Redact keys as ``redact_secrets`` does, and any string holding a URL."""
    if isinstance(value, dict):
        return {
            key: REDACTED if is_secret_key(key) else _scrub_urls(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_urls(item) for item in value]
    if isinstance(value, str) and "://" in value:
        return REDACTED
    return value


def redact_dps_value(key: object, value):
    """One DPS value made safe to log or put in a diagnostics dump.

    A value carrying JSON (plain or base64, like the DPS 212 alarm record) comes
    back decoded, with ``files`` and every URL redacted; the rest of the record
    (``cmd``, ``alarm``, ``time``) is kept, because that is what issues #42 and
    #61 were debugged from. A string holding a URL is redacted outright. A DPS
    212 value that cannot be decoded is redacted too, since its snapshot
    reference cannot be found and stripped.
    """
    if isinstance(value, (dict, list, tuple)):
        return _scrub_urls(value)
    if not isinstance(value, str):
        return value
    decoded = _decode_json_value(value)
    if decoded is not None:
        return _scrub_urls(decoded)
    if str(key) == DPS_ALARM_RECORD and value.strip():
        return f"{REDACTED} (undecoded, {len(value)} chars)"
    if "://" in value:
        return REDACTED
    return value


def redact_dps(dps: dict | None) -> dict | None:
    """A DPS dict with every value passed through ``redact_dps_value``."""
    if dps is None:
        return None
    return {key: redact_dps_value(key, value) for key, value in dps.items()}
