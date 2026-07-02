from __future__ import annotations

import time


class CircuitBreaker:
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, threshold: int = 3, cooldown_seconds: int = 60) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.state = self.STATE_CLOSED
        self.opened_at: float = 0.0

    def record_success(self) -> None:
        if self.state == self.STATE_HALF_OPEN:
            self.state = self.STATE_CLOSED
        self.failures = 0
        self.opened_at = 0.0

    def record_failure(self) -> None:
        if self.state == self.STATE_HALF_OPEN:
            self.state = self.STATE_OPEN
            self.opened_at = time.time()
            return
        self.failures += 1
        if self.failures >= self.threshold:
            self.state = self.STATE_OPEN
            self.opened_at = time.time()

    def allow(self) -> bool:
        if self.state == self.STATE_CLOSED:
            return True
        if self.state == self.STATE_OPEN:
            if time.time() - self.opened_at >= self.cooldown_seconds:
                self.state = self.STATE_HALF_OPEN
                return True
            return False
        # HALF_OPEN
        return True
