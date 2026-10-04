"""Tests for the Tuya API signing algorithm."""

import hashlib

import pytest

# Import the signing internals
from api import PhilipsAventAPI, _sign, _swap, keys_from_data, normalize_keys

from tests.test_philips_avent._fake_keys import FAKE_KEYS, real_keys

SK = FAKE_KEYS.signing_key


class TestSwapSignString:
    def test_swap_32_chars(self):
        assert _swap("AAAAAAAABBBBBBBBCCCCCCCCDDDDDDDD") == "BBBBBBBBAAAAAAAADDDDDDDDCCCCCCCC"

    def test_swap_preserves_non_32(self):
        assert _swap("short") == "short"
        assert _swap("") == ""

    def test_swap_known_value(self):
        # From Frida capture: 18634a7fd67b6366cca3137388c3a9fc → d67b636618634a7f88c3a9fccca31373
        assert _swap("18634a7fd67b6366cca3137388c3a9fc") == "d67b636618634a7f88c3a9fccca31373"


class TestSign:
    def test_known_vector(self):
        # Fixed vector computed with the real app keys (a made-up sid and device
        # id, not a captured session). Runs only when the real keys are in the
        # environment, because they are not in this repository.
        keys = real_keys()
        if keys is None:
            pytest.skip("AVENT_APP_KEY / AVENT_SIGNING_KEY / AVENT_CH_KEY not set")
        params = {
            "a": "smartlife.p.time.get",
            "v": "1.0",
            "et": "0.0.1",
            "time": "1776696747",
            "requestId": "test-1234",
            "sid": "eu000000test0000000000000000000000000000000000000000000000",
            "deviceId": "0123456789abcdef0123456789abcdef",
            "appVersion": "1.8.0",
            "ttid": f"sdk_international@{keys.app_key}",
            "os": "Android",
            "lang": "en_US",
            "chKey": keys.ch_key,
        }
        result = _sign(params, keys.signing_key)
        assert result == "59170c85ef0c5044c419be5b2824591b60acaf87e75536954779e481db52e253"

    def test_sign_depends_on_signing_key(self):
        params = {"a": "test", "v": "1.0", "time": "1"}
        assert _sign(params, "key-one") != _sign(params, "key-two")

    def test_sign_filters_non_whitelist(self):
        params_with_extra = {
            "a": "test",
            "v": "1.0",
            "time": "12345",
            "extraField": "should_be_ignored",
            "anotherOne": "also_ignored",
        }
        params_without = {
            "a": "test",
            "v": "1.0",
            "time": "12345",
        }
        assert _sign(params_with_extra, SK) == _sign(params_without, SK)

    def test_sign_with_postdata(self):
        params = {
            "a": "tuya.m.device.get",
            "v": "1.0",
            "time": "12345",
            "postData": '{"devId":"test123"}',
        }
        result = _sign(params, SK)
        assert len(result) == 64  # SHA-256 hex
        # postData should be MD5+swapped in the sign string
        assert result != _sign({**params, "postData": ""}, SK)

    def test_sign_empty_postdata_ignored(self):
        params1 = {"a": "test", "v": "1.0", "time": "1"}
        params2 = {"a": "test", "v": "1.0", "time": "1", "postData": ""}
        assert _sign(params1, SK) == _sign(params2, SK)


class TestEncryptPassword:
    def test_encrypt_produces_hex(self):
        # Use a known PEM key
        pb_key = (
            "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDV4UCuZgEhQ/bPa47kicAa"
            "+lqpvC7Zwh3KBD2Ar92AlgzbDaXCDwHXyi2VDSQtHhxvCXMBQwhBNsknIFsd2L"
            "rxMhCsLbTOmJ5+yWkbJZJS/S5to1HdDbGEyJTqnvpeMe6xE5k+g4yj2a8IQUH"
            "G4FrIorJayuIsAT33selsHylVjQIDAQAB"
        )
        result = PhilipsAventAPI.encrypt_password("TestPass123", pb_key)
        assert len(result) == 256  # RSA 1024-bit output = 128 bytes = 256 hex


class TestMQTTDerivation:
    def test_mqtt_password(self):
        # Known: MD5(MD5(signing_key) + ecode) middle 16
        ecode = "0000test0000test"
        md5_key = hashlib.md5(FAKE_KEYS.signing_key.encode()).hexdigest()
        full = hashlib.md5((md5_key + ecode).encode()).hexdigest()
        expected = full[8:24]

        result = PhilipsAventAPI(None, FAKE_KEYS).derive_mqtt_password(ecode)
        assert result == expected
        assert len(result) == 16

    def test_mqtt_username_format(self):
        result = PhilipsAventAPI(None, FAKE_KEYS).derive_mqtt_username(
            sid="test_sid",
            ecode="test_ecode",
            partner_identity="p1234",
        )
        assert result.startswith("p1234_v1_")
        assert f"_v1_{FAKE_KEYS.app_key}_{FAKE_KEYS.ch_key}_mb_" in result
        assert "_mb_test_sid" in result
        assert len(result.split("_mb_")[1]) > len("test_sid")  # has hash tail

    def test_mqtt_client_id_format(self):
        result = PhilipsAventAPI.derive_mqtt_client_id(
            uid="test_uid",
            device_id="test_device",
        )
        assert result.startswith("com.philips.ph.babymonitorplus_mb_")
        assert "test_device" in result
        assert result.endswith("_DEFAULT")


class TestKeys:
    def test_valid_keys_are_normalized(self):
        pasted_with_break = FAKE_KEYS.signing_key[:20] + "\n" + FAKE_KEYS.signing_key[20:]
        keys = normalize_keys(f" {FAKE_KEYS.app_key} ", pasted_with_break, "0123ABCD")
        assert keys == FAKE_KEYS

    def test_wrong_app_key_length_rejected(self):
        assert normalize_keys("short", FAKE_KEYS.signing_key, FAKE_KEYS.ch_key) is None

    def test_non_hex_ch_key_rejected(self):
        assert normalize_keys(FAKE_KEYS.app_key, FAKE_KEYS.signing_key, "zzzzzzzz") is None

    def test_signing_key_must_start_with_package(self):
        assert normalize_keys(FAKE_KEYS.app_key, FAKE_KEYS.app_key, FAKE_KEYS.ch_key) is None

    def test_keys_from_entry_data(self):
        data = {"app_key": FAKE_KEYS.app_key, "signing_key": FAKE_KEYS.signing_key, "ch_key": FAKE_KEYS.ch_key}
        assert keys_from_data(data) == FAKE_KEYS

    def test_entry_without_keys(self):
        assert keys_from_data({"sid": "x"}) is None
