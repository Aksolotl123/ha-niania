"""Tuya app keys for the tests.

The real keys are not in this repository. Most tests only need keys of the right
shape; the known-vector tests need the real ones and read them from the
environment (AVENT_APP_KEY, AVENT_SIGNING_KEY, AVENT_CH_KEY), skipping otherwise.
"""
import os

from api import TuyaKeys, normalize_keys

FAKE_KEYS = TuyaKeys(
    app_key="testappkey0123456789",
    signing_key="com.philips.ph.babymonitorplus_TEST_SIGNING_KEY",
    ch_key="0123abcd",
)


def real_keys() -> TuyaKeys | None:
    """The real app keys from the environment, or None when they are not set."""
    try:
        return normalize_keys(
            os.environ["AVENT_APP_KEY"], os.environ["AVENT_SIGNING_KEY"], os.environ["AVENT_CH_KEY"]
        )
    except KeyError:
        return None
