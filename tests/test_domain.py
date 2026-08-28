"""Tests for the pure rotation domain."""

import sys
from datetime import date, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from zoneinfo import ZoneInfo

spec = spec_from_file_location(
    "house_duty_domain", Path(__file__).parents[1] / "custom_components/house_duty/domain.py"
)
assert spec and spec.loader
domain = module_from_spec(spec)
sys.modules[spec.name] = domain
spec.loader.exec_module(domain)
Absence, Period, RotationState = domain.Absence, domain.Period, domain.RotationState
overlaps_period, period_bounds, period_for, resolve = (
    domain.overlaps_period,
    domain.period_bounds,
    domain.period_for,
    domain.resolve,
)
notification_recipients = domain.notification_recipients
configuration_preserves_rotation = domain.configuration_preserves_rotation


def test_basic_rotation() -> None:
    idx = 0
    results = []
    for week in range(4):
        assignment, idx = resolve(Period(date(2026, 1, 5 + 7 * week)), ["a", "b", "c"], idx, set())
        results.append(assignment.household_id)
    assert results == ["a", "b", "c", "a"]


def test_skips_are_consumed() -> None:
    first, idx = resolve(Period(date(2026, 1, 5)), ["a", "b", "c"], 0, {"a"})
    second, idx = resolve(Period(date(2026, 1, 12)), ["a", "b", "c"], idx, set())
    assert (first.household_id, first.skipped, second.household_id) == ("b", ("a",), "c")


def test_multiple_and_everyone_absent() -> None:
    assignment, idx = resolve(Period(date(2026, 1, 5)), ["a", "b", "c"], 0, {"a", "b"})
    assert assignment.household_id == "c" and idx == 0
    none, idx = resolve(Period(date(2026, 1, 12)), ["a", "b", "c"], idx, {"a", "b", "c"})
    assert none.problem and idx == 0


def test_reconciliation_missed_weeks() -> None:
    state = RotationState(Period(date(2025, 12, 29)), ["a", "b", "c"], 0)
    state.reconcile(Period(date(2026, 1, 19)), {"2026-01-05": {"b"}})
    assert [a.household_id for a in state.assignments.values()] == ["a", "c", "a", "b"]


def test_partial_overlap_and_dst() -> None:
    tz = ZoneInfo("Europe/Berlin")
    period = period_for(date(2026, 3, 23))
    absence = Absence(datetime(2026, 3, 29, 23, tzinfo=tz), datetime(2026, 3, 31, tzinfo=tz))
    assert overlaps_period(absence, period, tz)
    start, end = period_bounds(period, tz)
    assert start.hour == end.hour == 0
    assert (end.timestamp() - start.timestamp()) / 3600 == 167


def test_repeated_long_absence_and_year_boundary() -> None:
    state = RotationState.from_anchor(Period(date(2026, 12, 28)), ["a", "b", "c"], "a")
    state.reconcile(
        Period(date(2027, 1, 18)),
        {"2027-01-04": {"b"}, "2027-01-11": {"b"}, "2027-01-18": {"b"}},
    )
    assert [item.household_id for item in state.assignments.values()] == ["a", "c", "a", "c"]


def test_notification_routing() -> None:
    ids = ["a", "b", "c"]
    assert notification_recipients("garbage", "Biomüll", "Gelber Sack", "b", ids) == ["b"]
    assert notification_recipients("garbage", "New unknown type", "Gelber Sack", "b", ids) == ["b"]
    assert notification_recipients("garbage", "  GELBER   sack ", "Gelber Sack", "b", ids) == ids
    assert notification_recipients("chore", "Clean porch", "Gelber Sack", "c", ids) == ["c"]


def test_configuration_change_compatibility() -> None:
    # Renames and calendar/target changes do not alter stable IDs.
    assert configuration_preserves_rotation(["a", "b", "c"], ["a", "b", "c"])
    assert not configuration_preserves_rotation(["a", "b", "c"], ["b", "a", "c"])
    assert not configuration_preserves_rotation(["a", "b", "c"], ["a", "b", "c", "d"])
    assert not configuration_preserves_rotation(["a", "b", "c"], ["a", "c"])
