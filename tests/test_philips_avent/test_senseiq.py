"""Tests for the SenseIQ LAN data points (DPS 3 breathing, DPS 4 sleep)."""
import base64
import json

from senseiq import BreathingReading, parse_breathing, parse_sleep, sleep_stage_name

# A DPS 4 value as pushed by an SCD923 (base64 of hex of JSON).
SLEEP_PUSH = (
    "N2IyMjczNzQyMjNhMzEzNzM5MzEzMTMyMzMzOTM4MzkyYzIyNzM2NDIyM2EzNDM1MzQzNzJjMjI2MzczNzMyMjNhMjI2YzIy"
    "MmMyMjYzNzM3MzY0MjIzYTMxMzAzODMyMmMyMjczNzM2NDIyM2E1YjdiMjI2MTIyM2EzMzMwMzI3ZDJjN2IyMjZmMjIzYTM5"
    "MzIzMjdkMmM3YjIyNjQyMjNhMzIzMDMxMzQ3ZDJjN2IyMjZjMjIzYTMxMzQzMzdkMmM3YjIyNjQyMjNhMzgzNDdkNWQ3ZA=="
)


class TestBreathing:
    def test_still_reading_has_rate(self):
        reading = parse_breathing('{"r":"b","br":35}')
        assert reading == BreathingReading("b", 35)
        assert reading.breathing_rate == 35
        assert not reading.moving

    def test_moving_reading_has_no_rate(self):
        reading = parse_breathing('{"r":"m","br":0}')
        assert reading.moving
        assert reading.breathing_rate is None

    def test_still_with_zero_rate_is_unknown(self):
        assert parse_breathing('{"r":"b","br":0}').breathing_rate is None

    def test_unknown_reading_code_is_kept(self):
        reading = parse_breathing('{"r":"x"}')
        assert reading.reading == "x"
        assert reading.rate is None
        assert not reading.moving
        assert not reading.in_bed

    def test_still_and_moving_mean_in_bed(self):
        assert parse_breathing('{"r":"b","br":30}').in_bed
        assert parse_breathing('{"r":"m","br":0}').in_bed

    def test_garbage_is_ignored(self):
        assert parse_breathing("not json") is None
        assert parse_breathing('{"br":30}') is None
        assert parse_breathing(42) is None


class TestSleep:
    def test_real_push(self):
        sleep = parse_sleep(SLEEP_PUSH)
        assert sleep["in_bed_since"] == 1791123989
        assert sleep["duration"] == 4547
        assert sleep["stage"] == "light"
        assert sleep["stage_duration"] == 1082
        assert sleep["stages"] == [
            {"stage": "awake", "seconds": 302},
            {"stage": "other", "seconds": 922},
            {"stage": "deep", "seconds": 2014},
            {"stage": "light", "seconds": 143},
            {"stage": "deep", "seconds": 84},
        ]
        # Finished stages plus the current one add up to the session length.
        total = sum(s["seconds"] for s in sleep["stages"]) + sleep["stage_duration"]
        assert total == sleep["duration"]

    def test_plain_json_is_accepted(self):
        sleep = parse_sleep(json.dumps({"st": 1, "sd": 60, "css": "d", "cssd": 60, "ssd": []}))
        assert sleep["stage"] == "deep"
        assert sleep["stages"] == []

    def test_unknown_stage_code_is_passed_through(self):
        assert sleep_stage_name("z") == "z"
        assert sleep_stage_name(None) is None

    def test_garbage_is_ignored(self):
        assert parse_sleep("@@@") is None
        assert parse_sleep(base64.b64encode(b"zz").decode()) is None
        assert parse_sleep(None) is None
