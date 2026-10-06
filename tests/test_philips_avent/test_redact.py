"""Tests for the shared secret-redaction helper.

Two things depend on this being right. The diagnostics dump promises users it
strips their secrets, and docs/reporting-issues.md makes the same promise about
the debug log before asking them to attach it to a public issue. Discovery
responses carry ``localKey`` — a direct LAN control credential — inside lists
of device dicts, which is exactly the shape a non-recursive redactor misses.
"""

import base64
import json

import pytest
from redact import (
    ALLOWED_KEYS,
    IDENTIFIER_KEYS,
    REDACTED,
    SECRET_KEYS,
    is_secret_key,
    mask_id,
    normalize_key,
    redact_dps,
    redact_secrets,
)


class TestFlatDicts:
    def test_local_key_is_redacted(self):
        assert redact_secrets({"localKey": "abc"}) == {"localKey": "**REDACTED**"}

    def test_snake_case_spelling_is_redacted_too(self):
        assert redact_secrets({"local_key": "abc"}) == {"local_key": "**REDACTED**"}

    def test_key_matching_ignores_case(self):
        assert redact_secrets({"LocalKey": "abc"}) == {"LocalKey": "**REDACTED**"}

    def test_harmless_keys_survive_untouched(self):
        payload = {"name": "Baby", "category": "sp", "productId": "fakeproduct01"}
        assert redact_secrets(payload) == payload

    def test_device_id_is_redacted(self):
        # Not a credential, but it ties the monitor to its owner in a public issue.
        out = redact_secrets({"name": "Baby", "devId": "abc123"})
        assert out == {"name": "Baby", "devId": "**REDACTED**"}

    def test_session_credentials_are_redacted(self):
        out = redact_secrets({"sid": "s", "ecode": "e", "partnerIdentity": "p", "uid": "u"})
        assert set(out.values()) == {"**REDACTED**"}

    def test_household_coordinates_are_redacted(self):
        # Tuya home objects carry the household's position; a debug log
        # attached to a public issue should not hand it out.
        # The home id goes too: it identifies the household.
        out = redact_secrets({"gid": 123, "lat": "45.4", "lon": "9.1", "name": "Home"})
        assert out == {"gid": "**REDACTED**", "lat": "**REDACTED**", "lon": "**REDACTED**", "name": "Home"}


class TestNesting:
    def test_recurses_into_nested_dicts(self):
        out = redact_secrets({"device": {"inner": {"localKey": "abc"}}})
        assert out["device"]["inner"]["localKey"] == "**REDACTED**"

    def test_recurses_into_lists_of_dicts(self):
        # The gap that made discovery logging unsafe: cameras arrive as a list.
        payload = {"deviceList": [{"name": "a", "localKey": "secret"}]}
        out = redact_secrets(payload)
        assert out["deviceList"][0] == {"name": "a", "localKey": "**REDACTED**"}

    def test_redacts_a_bare_list_at_the_top_level(self):
        # discover_cameras logs the raw API result, which is a list, not a dict.
        out = redact_secrets([{"localKey": "secret"}, {"localKey": "other"}])
        assert out == [{"localKey": "**REDACTED**"}, {"localKey": "**REDACTED**"}]

    def test_recurses_through_lists_inside_lists(self):
        out = redact_secrets([[{"localKey": "secret"}]])
        assert out == [[{"localKey": "**REDACTED**"}]]

    def test_no_secret_value_survives_anywhere_in_the_output(self):
        payload = {"homes": [{"lat": "45.4", "rooms": [{"deviceList": [{"localKey": "leaked"}]}]}]}
        assert "leaked" not in repr(redact_secrets(payload))
        assert "45.4" not in repr(redact_secrets(payload))


class TestNonMappings:
    def test_scalars_pass_through(self):
        assert redact_secrets("hello") == "hello"
        assert redact_secrets(7) == 7
        assert redact_secrets(None) is None

    def test_tuples_are_traversed_and_returned_as_lists(self):
        assert redact_secrets(({"localKey": "abc"},)) == [{"localKey": "**REDACTED**"}]

    def test_input_is_not_mutated(self):
        payload = {"localKey": "abc"}
        redact_secrets(payload)
        assert payload == {"localKey": "abc"}


class TestSecretKeys:
    def test_key_sets_are_declared_normalised(self):
        # Matching normalises the incoming key, so an entry with upper case or
        # an underscore here would silently never match.
        for key in SECRET_KEYS | IDENTIFIER_KEYS | ALLOWED_KEYS:
            assert key == normalize_key(key)


class TestLooseKeyMatching:
    """Exact-name matching let these through in plain text (audit 2026-10-05)."""

    @pytest.mark.parametrize(
        "key",
        [
            "accessToken", "refreshToken", "access_token", "refresh-token", "h5Token",
            "secKey", "localKeyV2", "local_key_v2", "authKey", "p2pKey", "sessionKey",
            "mqttPassword", "password", "passwd", "PASSWORD", "loginPwd",
            "credential", "credentials", "clientSecret", "client_secret", "secret",
            "localKey", "LocalKey", "local_key", "LOCAL-KEY",
        ],
    )
    def test_secret_looking_keys_are_redacted(self, key):
        assert redact_secrets({key: "fake-value-123"}) == {key: REDACTED}

    @pytest.mark.parametrize(
        "key",
        [
            "ip", "IP", "lanIp", "mac", "uuid", "devId", "deviceId", "device_id",
            "camera_id", "cameraId", "gid", "ownerId", "sn", "serial", "serialNumber",
            "id", "homeId", "gwId", "ssid",
        ],
    )
    def test_identifiers_are_redacted(self, key):
        assert redact_secrets({key: "fake-id-123"}) == {key: REDACTED}

    @pytest.mark.parametrize(
        "key",
        [
            "name", "productId", "product_id", "productKey", "temperature", "category",
            "keyboard", "monkey", "keyword", "icon", "online", "timeZoneId", "dps",
            "api_host", "country_code", "talkback", "version", "time", "cmd", "alarm",
        ],
    )
    def test_ordinary_fields_are_not_redacted(self, key):
        assert not is_secret_key(key)
        assert redact_secrets({key: "value"}) == {key: "value"}

    def test_config_entry_shape(self):
        entry = {
            "email": "someone@example.invalid",
            "sid": "fakesid",
            "ecode": "fakeecode",
            "partner": "fakepartner",
            "uid": "fakeuid",
            "device_id": "fakephoneid0123",
            "app_key": "fakeappkey",
            "signing_key": "fakesigningkey",
            "ch_key": "fakechkey",
            "api_host": "https://a1.example.invalid",
            "country_code": "48",
            "cameras": [{"id": "fakecamid0123", "name": "Baby", "product_id": "fakeproduct01"}],
        }
        out = redact_secrets(entry)
        for leaked in ("someone@", "fakesid", "fakeecode", "fakepartner", "fakeuid",
                       "fakephoneid", "fakeappkey", "fakesigningkey", "fakechkey", "fakecamid"):
            assert leaked not in repr(out)
        assert out["cameras"][0]["name"] == "Baby"
        assert out["cameras"][0]["product_id"] == "fakeproduct01"
        assert out["country_code"] == "48"

    def test_nested_suffixed_keys_in_discovery_lists(self):
        payload = {
            "homes": [
                {
                    "gid": 1,
                    "name": "Home",
                    "rooms": [
                        {
                            "deviceList": [
                                {
                                    "devId": "fakedev0001",
                                    "localKeyV2": "fakelk",
                                    "p2pKey": "fakep2p",
                                    "ip": "203.0.113.7",
                                    "mac": "00:00:5e:00:53:01",
                                    "uuid": "fakeuuid",
                                    "productId": "fakeproduct01",
                                    "name": "Baby",
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        out = redact_secrets(payload)
        text = repr(out)
        for leaked in ("fakedev0001", "fakelk", "fakep2p", "203.0.113.7", "00:00:5e", "fakeuuid"):
            assert leaked not in text
        device = out["homes"][0]["rooms"][0]["deviceList"][0]
        assert device["productId"] == "fakeproduct01"
        assert device["name"] == "Baby"


def _alarm_record(**fields) -> str:
    record = {
        "v": "4.0",
        "cmd": "ipc_baby_cry",
        "alarm": True,
        "time": 1783686591,
        "files": [["fake-bucket", "/fake/path/snapshot.jpeg", "fakeencryptkey"]],
    }
    record.update(fields)
    return base64.b64encode(json.dumps(record).encode()).decode()


class TestRedactDps:
    """The DPS dump in diagnostics and the DPS debug lines (audit 2026-10-05)."""

    def test_alarm_record_files_are_stripped_but_event_kept(self):
        out = redact_dps({"212": _alarm_record()})["212"]
        assert out["files"] == REDACTED
        assert out["cmd"] == "ipc_baby_cry"
        assert out["time"] == 1783686591
        assert out["alarm"] is True
        assert "fake-bucket" not in repr(out)
        assert "snapshot.jpeg" not in repr(out)

    def test_plain_json_alarm_record(self):
        raw = json.dumps({"cmd": "ipc_motion", "files": ["x"], "url": "https://example.invalid/a.jpg"})
        out = redact_dps({"212": raw})["212"]
        assert out == {"cmd": "ipc_motion", "files": REDACTED, "url": REDACTED}

    def test_urls_anywhere_in_a_decoded_record_are_stripped(self):
        out = redact_dps({"212": _alarm_record(extra={"pic": "https://example.invalid/p.jpg"})})
        assert "example.invalid" not in repr(out)

    def test_undecodable_alarm_record_is_redacted(self):
        out = redact_dps({"212": "not-base64-json!!"})["212"]
        assert out.startswith(REDACTED)
        assert "not-base64" not in out

    def test_other_dps_carrying_files_are_stripped(self):
        out = redact_dps({"185": _alarm_record(cmd="ipc_motion")})["185"]
        assert out["files"] == REDACTED

    def test_bare_url_value_is_redacted(self):
        assert redact_dps({"150": "https://example.invalid/clip.mp4"}) == {"150": REDACTED}

    def test_ordinary_dps_are_untouched(self):
        dps = {"101": True, "103": 0, "141": "decibel_upload", "201": "play", "207": 2310, "212": ""}
        assert redact_dps(dps) == dps

    def test_url_inside_base64_text_is_redacted(self):
        raw = base64.b64encode(b"https://example.invalid/fake-bucket/a.jpeg").decode()
        out = redact_dps({"150": raw})["150"]
        assert out.startswith(REDACTED)
        assert raw not in out

    def test_double_base64_json_is_decoded_and_scrubbed(self):
        out = redact_dps({"185": base64.b64encode(_alarm_record().encode()).decode()})["185"]
        assert out["files"] == REDACTED
        assert out["cmd"] == "ipc_baby_cry"
        assert "fake-bucket" not in repr(out)

    def test_base64_of_hex_of_json_is_decoded_and_scrubbed(self):
        # The DPS 4 shape (senseiq.py): base64 of hex of JSON.
        inner = json.dumps({"s": "a", "url": "https://example.invalid/x", "localKey": "fakekey"})
        raw = base64.b64encode(inner.encode().hex().encode()).decode()
        out = redact_dps({"4": raw})["4"]
        assert out == {"s": "a", "url": REDACTED, "localKey": REDACTED}

    @pytest.mark.parametrize("value", ["true", "0000", "abcd", "play", "decibel_upload", "MTIz"])
    def test_short_values_that_happen_to_be_base64_are_untouched(self, value):
        assert redact_dps({"141": value}) == {"141": value}

    def test_none_and_input_not_mutated(self):
        assert redact_dps(None) is None
        dps = {"212": _alarm_record()}
        before = dict(dps)
        redact_dps(dps)
        assert dps == before


class TestMaskId:
    def test_keeps_only_the_last_four_characters(self):
        assert mask_id("fakedevice0123abcd") == "***abcd"

    def test_short_or_missing_values_are_fully_masked(self):
        assert mask_id("abc") == "***"
        assert mask_id(None) == "***"
        assert mask_id(1234) == "***"
