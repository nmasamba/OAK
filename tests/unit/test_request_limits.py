# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-034 (RR-024): the token-bucket limiter and the `OAK_*` limit values."""

from __future__ import annotations

import pytest

from oak.bootstrap import MAXIMUM_LIMIT, read_limit
from oak.domain import OAKError
from oak.interfaces.api.limits import (
    DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS,
    DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT,
    RequestLimits,
    TokenBucketLimiter,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_a_key_may_burst_its_minute_and_then_waits_for_the_refill() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(60, clock=clock)  # one token a second
    assert all(limiter.admit("a") is None for _ in range(60))
    assert limiter.admit("a") == 1
    clock.now += 0.5
    assert limiter.admit("a") == 1, "half a token is not a request"
    clock.now += 0.5
    assert limiter.admit("a") is None, "a whole token came back"
    assert limiter.admit("a") == 1
    assert limiter.admit("b") is None, "keys are independent"
    assert len(limiter) == 2


def test_the_wait_is_the_shortfall_in_whole_seconds_at_least_one() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(6, clock=clock)  # a token every ten seconds
    for _ in range(6):
        assert limiter.admit("k") is None
    assert limiter.admit("k") == 10
    clock.now += 4
    assert limiter.admit("k") == 6
    clock.now += 6
    assert limiter.admit("k") is None
    assert limiter.admit("k") == 10


def test_a_clock_that_goes_backwards_never_grants_tokens() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(2, clock=clock)
    assert limiter.admit("k") is None and limiter.admit("k") is None
    clock.now -= 100
    assert limiter.admit("k") == 30, "a backwards clock refilled the bucket"


def test_zero_switches_the_limit_off_and_remembers_nothing() -> None:
    limiter = TokenBucketLimiter(0)
    assert not limiter.enabled
    assert all(limiter.admit("k") is None for _ in range(1_000))
    assert len(limiter) == 0


def test_the_limiter_forgets_the_least_recently_seen_key_past_its_capacity() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(1, clock=clock, capacity=2)
    assert limiter.admit("a") is None
    assert limiter.admit("b") is None
    assert limiter.admit("c") is None
    assert len(limiter) == 2
    assert limiter.admit("b") == 60, "a remembered key is still limited"
    assert limiter.admit("a") is None, "the forgotten key starts afresh"


def test_the_limits_come_from_the_environment_and_a_bad_value_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("OAK_REQUESTS_PER_MINUTE_PER_ADDRESS", "OAK_REQUESTS_PER_MINUTE_PER_TENANT"):
        monkeypatch.delenv(name, raising=False)
    limits = RequestLimits.from_environment()
    assert (limits.per_address, limits.per_tenant) == (
        DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS,
        DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT,
    )
    assert DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS >= 600, "generous for one address"
    assert DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT >= DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS
    monkeypatch.setenv("OAK_REQUESTS_PER_MINUTE_PER_ADDRESS", "0")
    monkeypatch.setenv("OAK_REQUESTS_PER_MINUTE_PER_TENANT", " 12 ")
    limits = RequestLimits.from_environment()
    assert (limits.per_address, limits.per_tenant) == (0, 12)
    for bad in ("many", "-1", str(MAXIMUM_LIMIT + 1), "1.5"):
        monkeypatch.setenv("OAK_LIMIT_TEST", bad)
        with pytest.raises(OAKError) as refusal:
            read_limit("OAK_LIMIT_TEST", 7)
        assert refusal.value.code == "OAK-LIMIT-CONFIG"
        assert "OAK_LIMIT_TEST" in refusal.value.message
    monkeypatch.setenv("OAK_LIMIT_TEST", str(MAXIMUM_LIMIT))
    assert read_limit("OAK_LIMIT_TEST", 7) == MAXIMUM_LIMIT
    monkeypatch.setenv("OAK_LIMIT_TEST", "")
    assert read_limit("OAK_LIMIT_TEST", 7) == 7


def test_a_limited_key_survives_a_flood_of_fresh_keys() -> None:
    """Review L3: eviction forgets keys that owe nothing, never a key in debt, so a
    stream of invented keys cannot reset a limit."""

    clock = _Clock()
    limiter = TokenBucketLimiter(2, clock=clock, capacity=8)
    assert limiter.admit("debtor") is None and limiter.admit("debtor") is None
    assert limiter.admit("debtor") == 30
    for index in range(50):
        assert limiter.admit(f"fresh-{index}") is None
    assert len(limiter) <= 8
    assert limiter.admit("debtor") == 30, "the flood evicted the key in debt"
