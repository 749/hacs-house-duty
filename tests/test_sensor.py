"""Sensor presentation tests."""

from datetime import date
from types import SimpleNamespace

from custom_components.house_duty.domain import Assignment, Period
from custom_components.house_duty.sensor import HouseDutyNext


def _entity(assignment: Assignment) -> HouseDutyNext:
    coordinator = SimpleNamespace(
        households=[{"id": "a", "name": "Apartment A"}, {"id": "b", "name": "Apartment B"}],
        next_assignment=assignment,
        translations={
            "component.house_duty.common.no_household_available": "Kein Haushalt verfügbar"
        },
        next_unavailable_calendars=[],
    )
    entry = SimpleNamespace(entry_id="entry", runtime_data=coordinator)
    return HouseDutyNext(entry)


def test_next_sensor_displays_assigned_household() -> None:
    period = Period(date(2026, 8, 31))
    entity = _entity(Assignment(period, "b", "b"))

    assert entity.native_value == "Apartment B"
    assert "reason" not in entity.extra_state_attributes


def test_next_sensor_explains_when_everyone_is_absent() -> None:
    period = Period(date(2026, 8, 31))
    entity = _entity(Assignment(period, None, "a", ("a", "b")))

    assert entity.native_value == "Kein Haushalt verfügbar"
    assert entity.extra_state_attributes == {
        "duty_period_start": "2026-08-31",
        "duty_period_end": "2026-09-07",
        "originally_next_household": "Apartment A",
        "skipped_households": ["Apartment A", "Apartment B"],
        "reason": "all_households_absent",
    }
