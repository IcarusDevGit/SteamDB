"""Bounded, provider-specific asynchronous request scheduling."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from workflow_progress import Reporter, emit


T = TypeVar("T")


class RetryableRequestError(RuntimeError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AsyncRateLimiter:
    """Serialize request starts at a configurable minimum interval."""

    def __init__(
        self,
        interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if interval < 0:
            raise ValueError("interval cannot be negative")
        self.interval = interval
        self._clock = clock
        self._sleep = sleep
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_start - now)
            if delay:
                await self._sleep(delay)
                now = self._clock()
            self._next_start = max(now, self._next_start) + self.interval

    async def defer(self, delay: float) -> None:
        async with self._lock:
            self._next_start = max(self._next_start, self._clock() + max(0.0, delay))


@dataclass(frozen=True)
class ProviderPolicy:
    interval: float
    concurrency: int
    queue_size: int
    retries: int = 3
    backoff_base: float = 0.5


class ProviderGate:
    """Rate, concurrency, queue, and retry boundary for one provider."""

    def __init__(
        self,
        policy: ProviderPolicy,
        *,
        provider: str = "unknown",
        reporter: Reporter | None = None,
        limiter: AsyncRateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ):
        if policy.concurrency < 1 or policy.queue_size < 1:
            raise ValueError("provider concurrency and queue size must be positive")
        self.policy = policy
        self.provider = provider
        self.reporter = reporter
        self.limiter = limiter or AsyncRateLimiter(policy.interval, sleep=sleep)
        self._in_flight = asyncio.Semaphore(policy.concurrency)
        self._admitted = asyncio.Semaphore(policy.queue_size)
        self._sleep = sleep
        self._jitter = jitter

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        async with self._admitted:
            for attempt in range(self.policy.retries + 1):
                await self.limiter.acquire()
                try:
                    async with self._in_flight:
                        return await operation()
                except RetryableRequestError as exc:
                    if attempt >= self.policy.retries:
                        raise
                    delay = exc.retry_after
                    if delay is None:
                        ceiling = self.policy.backoff_base * (2**attempt)
                        delay = self._jitter(ceiling / 2, ceiling)
                    emit(
                        self.reporter,
                        "provider_retry",
                        provider=self.provider,
                        attempt=attempt + 2,
                        max_attempts=self.policy.retries + 1,
                        wait_seconds=round(delay, 3),
                    )
                    await self.limiter.defer(delay)
                    await self._sleep(delay)
        raise RuntimeError("unreachable provider gate state")


DEFAULT_POLICIES = {
    "steam_web": ProviderPolicy(interval=1.0, concurrency=1, queue_size=100),
    "steam_store": ProviderPolicy(interval=1.0, concurrency=2, queue_size=100),
    "itad": ProviderPolicy(interval=0.3, concurrency=4, queue_size=200),
}
