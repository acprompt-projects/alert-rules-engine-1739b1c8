import time
import threading


class RateLimiter:
    """Token-bucket rate limiter, thread-safe."""

    def __init__(self, max_tokens: int = 10, refill_period: float = 60.0):
        self.max_tokens = max_tokens
        self.refill_period = refill_period
        self._tokens: float = float(max_tokens)
        self._last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.max_tokens,
                self._tokens + elapsed * (self.max_tokens / self.refill_period),
            )
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False