from __future__ import annotations

import random
import time
from dataclasses import dataclass

from firexcore_mailvault.errors import BandwidthLimitReached
from firexcore_mailvault.repository import ArchiveRepository


@dataclass(frozen=True, slots=True)
class ThrottleSettings:
    delay_min_ms: int
    delay_max_ms: int
    pause_every_messages: int
    pause_min_seconds: int
    pause_max_seconds: int
    soft_cap_bytes: int
    hard_cap_bytes: int


class BandwidthThrottle:
    def __init__(
        self,
        repository: ArchiveRepository,
        account_id: int,
        run_id: int,
        settings: ThrottleSettings,
    ) -> None:
        self.repository = repository
        self.account_id = account_id
        self.run_id = run_id
        self.settings = settings
        self.raw_messages_this_run = 0

    def assert_can_fetch(self, expected_bytes: int) -> int:
        used = self.repository.rolling_bandwidth(self.account_id)
        if used >= self.settings.soft_cap_bytes:
            raise BandwidthLimitReached(f"Rolling 24-hour soft cap reached ({used} bytes used).")
        if used + expected_bytes > self.settings.hard_cap_bytes:
            raise BandwidthLimitReached(
                "The next message would exceed the rolling 24-hour hard cap "
                f"({used} + {expected_bytes} > {self.settings.hard_cap_bytes})."
            )
        return used

    def record(self, byte_count: int, kind: str) -> None:
        self.repository.record_bandwidth(self.account_id, byte_count, kind=kind, run_id=self.run_id)

    def after_raw_fetch(self) -> None:
        self.raw_messages_this_run += 1
        delay = random.uniform(self.settings.delay_min_ms, self.settings.delay_max_ms) / 1000
        if delay > 0:
            time.sleep(delay)
        if (
            self.settings.pause_every_messages > 0
            and self.raw_messages_this_run % self.settings.pause_every_messages == 0
        ):
            time.sleep(
                random.uniform(
                    self.settings.pause_min_seconds,
                    self.settings.pause_max_seconds,
                )
            )
