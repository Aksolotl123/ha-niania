"""LAN signalling for the bridge: address publishing, credentials and the JSON contract.

Ported behaviour from upstream aventproxy 2026.11.0: the bridge streams with
LAN signalling only when each camera carries ``local_key``, ``p2p_password``,
``lan_ip`` and ``lan_protocol`` and the config carries the account ``uid``.
"""

import asyncio
import json

from lan_credentials import fetch_missing_passwords, fetch_p2p_passwords, lan_credentials
from lan_policy import AddressPublisher, protocol_label
from payload import build_bridge_config, build_cameras_payload, previous_lan_values
from redact import redact_secrets as redact

CAM = {"deviceId": "cam1", "deviceName": "Baby", "productId": "p1"}
LAN = {"cam1": {"local_key": "k" * 16, "p2p_password": "pw", "lan_ip": "10.0.0.5", "lan_protocol": "3.5"}}


def _config(**overrides):
    args = dict(
        signing_key="s", sid="sid", ecode="e", partner="p", app_key="a", device_id="d",
        package_name="pkg", api_host="h", bridge_port=38554, cameras=[CAM],
    )
    args.update(overrides)
    return build_bridge_config(**args)


class TestProtocolLabel:
    def test_formats_like_the_bridge_expects(self):
        assert protocol_label(3.5) == "3.5"
        assert protocol_label(3.3) == "3.3"

    def test_unknown_is_empty(self):
        assert protocol_label(None) == ""


class TestAddressPublisher:
    def test_new_complete_pair_is_reported(self):
        seen = []
        pub = AddressPublisher(seen.append)
        pub.update("10.0.0.5", "3.5")
        assert seen == ["10.0.0.5"]
        assert (pub.last, pub.protocol) == ("10.0.0.5", "3.5")

    def test_seeded_pair_stays_silent(self):
        # A restart at the same address must not rewrite the file (and restart the bridge).
        seen = []
        pub = AddressPublisher(seen.append, "10.0.0.5", "3.5")
        pub.update("10.0.0.5", "3.5")
        assert seen == []

    def test_lost_address_or_unknown_protocol_says_nothing(self):
        seen = []
        pub = AddressPublisher(seen.append, "10.0.0.5", "3.5")
        pub.update(None, "3.5")
        pub.update("10.0.0.6", "")
        assert seen == []
        assert pub.last == "10.0.0.5"

    def test_moved_monitor_is_reported(self):
        seen = []
        pub = AddressPublisher(seen.append, "10.0.0.5", "3.5")
        pub.update("10.0.0.6", "3.5")
        assert seen == ["10.0.0.6"]


class TestBridgeJson:
    def test_lan_fields_and_uid_reach_the_bridge(self):
        cfg = _config(uid="u1", lan=LAN)
        assert cfg["uid"] == "u1"
        assert cfg["lan_streaming"] is True
        cam = cfg["cameras"][0]
        assert cam["local_key"] == "k" * 16
        assert cam["p2p_password"] == "pw"
        assert (cam["lan_ip"], cam["lan_protocol"]) == ("10.0.0.5", "3.5")

    def test_missing_lan_values_are_empty_strings(self):
        cam = build_cameras_payload([CAM])[0]
        assert {cam[k] for k in ("local_key", "p2p_password", "lan_ip", "lan_protocol")} == {""}

    def test_previous_values_round_trip(self):
        text = json.dumps(_config(uid="u1", lan=LAN))
        assert previous_lan_values(text) == {"cam1": {"lan_ip": "10.0.0.5", "lan_protocol": "3.5", "p2p_password": "pw"}}

    def test_previous_values_from_corrupt_or_old_file(self):
        assert previous_lan_values("") == {}
        assert previous_lan_values("{not json") == {}
        # A file written before LAN streaming: cameras without the new fields.
        old = json.dumps({"cameras": [{"camera_id": "cam1", "camera_name": "Baby", "product_id": "p1"}]})
        assert previous_lan_values(old) == {"cam1": {"lan_ip": "", "lan_protocol": "", "p2p_password": ""}}

    def test_secrets_are_redacted_in_diagnostics(self):
        redacted = redact(_config(uid="u1", lan=LAN))
        cam = redacted["cameras"][0]
        assert cam["p2p_password"] != "pw"
        assert cam["local_key"] != "k" * 16
        assert redacted["uid"] != "u1"


class FakeApi:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    async def get_rtc_config(self, cam_id):
        self.calls.append(cam_id)
        answer = self.answers[cam_id]
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeCoordinator:
    def __init__(self, local_key="", cloud_key="", lan_ip=None, lan_protocol=""):
        self.local_key = local_key
        self.device_info = {"localKey": cloud_key} if cloud_key else {}
        self.lan_ip = lan_ip
        self.lan_protocol = lan_protocol


class TestCredentials:
    def test_password_comes_from_rtc_config(self):
        api = FakeApi({"cam1": {"password": "fresh"}})
        assert asyncio.run(fetch_p2p_passwords(api, ["cam1"], {"cam1": "old"})) == {"cam1": "fresh"}

    def test_cloud_failure_keeps_previous_password(self):
        api = FakeApi({"cam1": OSError("cloud down")})
        assert asyncio.run(fetch_p2p_passwords(api, ["cam1"], {"cam1": "old"})) == {"cam1": "old"}

    def test_refetch_only_asks_for_missing(self):
        api = FakeApi({"cam2": {"password": "p2"}})
        got = asyncio.run(fetch_missing_passwords(api, ["cam1", "cam2"], {"cam1": "have"}))
        assert got == {"cam2": "p2"}
        assert api.calls == ["cam2"]

    def test_rotated_cloud_key_wins(self):
        coord = FakeCoordinator(local_key="old" * 5 + "x", cloud_key="n" * 16, lan_ip="10.0.0.5", lan_protocol="3.5")
        creds = lan_credentials({"cam1": coord}, {"cam1": "pw"})
        assert creds == {"cam1": {"local_key": "n" * 16, "p2p_password": "pw", "lan_ip": "10.0.0.5", "lan_protocol": "3.5"}}

    def test_no_session_yet_gives_empty_address(self):
        creds = lan_credentials({"cam1": FakeCoordinator(local_key="k" * 16)}, {})
        assert creds["cam1"]["lan_ip"] == "" and creds["cam1"]["p2p_password"] == ""
