# SPDX-License-Identifier: Apache-2.0
"""Per-address and per-tenant request limits for the API (RR-024).

A token bucket per key: a key may burst up to a minute's allowance and then continues at
that allowance per minute. The state lives in the one API process Community runs; nothing
is shared between processes or hosts, and nothing here is claimed to be distributed. A
refusal says how long to wait (`Retry-After`, whole seconds, at least one). The keys are
the client address, as the server sees it, and the tenant the request claims; neither is
logged (`oak.interfaces.logs.ALLOWED_FIELDS` leaves the address out by design), and a
limiter remembers at most `KEY_CAPACITY` keys, forgetting the least recently seen.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from oak.bootstrap import read_limit

DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS = 1_200
DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT = 6_000
KEY_CAPACITY = 4_096
EXEMPT_PATHS = frozenset({"/healthz", "/readyz"})


@dataclass(frozen=True, slots=True)
class RequestLimits:
    """Requests per minute per client address and per tenant; `0` switches a limit off."""

    per_address: int = DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS
    per_tenant: int = DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)

    @classmethod
    def from_environment(cls) -> RequestLimits:
        """`OAK_REQUESTS_PER_MINUTE_PER_ADDRESS` and `OAK_REQUESTS_PER_MINUTE_PER_TENANT`."""

        return cls(
            per_address=read_limit(
                "OAK_REQUESTS_PER_MINUTE_PER_ADDRESS", DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS
            ),
            per_tenant=read_limit(
                "OAK_REQUESTS_PER_MINUTE_PER_TENANT", DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT
            ),
        )


class TokenBucketLimiter:
    """One bucket per key, refilled continuously at `per_minute` tokens a minute."""

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        capacity: int = KEY_CAPACITY,
    ) -> None:
        self._burst = float(max(0, per_minute))
        self._rate = self._burst / 60.0
        self._clock = clock
        self._capacity = max(1, capacity)
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._burst > 0

    def admit(self, key: str) -> int | None:
        """`None` when the request is admitted; otherwise the whole seconds to wait."""

        if not self.enabled:
            return None
        now = self._clock()
        with self._lock:
            tokens, updated = self._buckets.get(key, (self._burst, now))
            tokens = min(self._burst, tokens + max(0.0, now - updated) * self._rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                self._buckets.move_to_end(key)
                while len(self._buckets) > self._capacity:
                    self._buckets.popitem(last=False)
                return None
            self._buckets[key] = (tokens, now)
            self._buckets.move_to_end(key)
            return max(1, math.ceil((1.0 - tokens) / self._rate))

    def __len__(self) -> int:
        return len(self._buckets)


__all__ = [
    "DEFAULT_REQUESTS_PER_MINUTE_PER_ADDRESS",
    "DEFAULT_REQUESTS_PER_MINUTE_PER_TENANT",
    "EXEMPT_PATHS",
    "KEY_CAPACITY",
    "RequestLimits",
    "TokenBucketLimiter",
]
