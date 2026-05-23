"""Tests for the 6-week training-block templates."""

from __future__ import annotations

from datetime import date, timedelta

from gymapp.services.coaching.blocks import (
    BLOCK_LENGTH_WEEKS,
    block_status,
    block_template,
    current_week_index,
)


def test_each_style_has_six_weeks_ending_in_deload():
    for style in ("bodybuilding", "powerlifting", "powerbuilding"):
        weeks = block_template(style)
        assert len(weeks) == BLOCK_LENGTH_WEEKS
        assert weeks[-1].is_deload is True
        assert all(w.week == i + 1 for i, w in enumerate(weeks))


def test_unknown_style_falls_back():
    assert block_template("zzz") == block_template("powerbuilding")


def test_current_week_index_advances_weekly():
    start = date(2026, 5, 1)
    assert current_week_index(start, date(2026, 5, 1)) == 1
    assert current_week_index(start, date(2026, 5, 7)) == 1   # day 6
    assert current_week_index(start, date(2026, 5, 8)) == 2   # day 7
    assert current_week_index(start, date(2026, 5, 15)) == 3


def test_current_week_index_floor_at_one():
    # a future start (shouldn't happen) still reads as week 1
    assert current_week_index(date(2026, 5, 10), date(2026, 5, 1)) == 1


def test_block_status_current_week():
    start = date(2026, 5, 1)
    status = block_status("powerlifting", start, date(2026, 5, 10))  # week 2
    assert status.week_index == 2
    assert status.is_finished is False
    assert status.current.week == 2
    assert len(status.weeks) == BLOCK_LENGTH_WEEKS


def test_block_status_finished_after_length():
    start = date(2026, 5, 1)
    later = start + timedelta(weeks=BLOCK_LENGTH_WEEKS)  # day 42 → week 7
    status = block_status("bodybuilding", start, later)
    assert status.is_finished is True
    assert status.current is None
    assert status.week_index == BLOCK_LENGTH_WEEKS  # capped for display
