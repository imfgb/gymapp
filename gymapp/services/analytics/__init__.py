"""Analytics service — Phase 4.

Volume + intensity rollups, PR cadence, weekly summary stats. Interface stub
only in Phase 0.
"""
from __future__ import annotations

from typing import Protocol


class AnalyticsStrategy(Protocol):
    def weekly_volume(self, user_id: int, week_start_iso: str) -> dict[str, float]:
        ...


class DeterministicAnalytics:
    def weekly_volume(self, user_id: int, week_start_iso: str) -> dict[str, float]:
        return {}
