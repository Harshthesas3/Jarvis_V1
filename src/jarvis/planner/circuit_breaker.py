import time
import threading
from typing import Optional

class _CircuitBreaker:
    def __init__(self, max_failures: int = 5, reset_seconds: int = 60):
        self.max_failures = max_failures
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.lock = threading.Lock()

    def record_failure(self):
        with self.lock:
            self.failures += 1
            self.last_failure_time = time.time()

            if self.failures >= self.max_failures:
                self.state = "OPEN"

    def record_success(self):
        with self.lock:
            if self.state != "CLOSED":
                self.state = "CLOSED"
            self.failures = 0
            self.last_failure_time = None

    def is_open(self) -> bool:
        with self.lock:
            if self.state == "OPEN":
                if self.last_failure_time:
                    if time.time() - self.last_failure_time >= self.reset_seconds:
                        self.state = "HALF_OPEN"
                        return False
                    return True
            return False

    def is_half_open(self) -> bool:
        with self.lock:
            return self.state == "HALF_OPEN"


_CIRCUIT_BREAKER = _CircuitBreaker()


def get_circuit_breaker() -> _CircuitBreaker:
    return _CIRCUIT_BREAKER