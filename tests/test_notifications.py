"""Notification behavior tests using lightweight Home Assistant fakes."""

from datetime import date
from types import SimpleNamespace

import pytest

from custom_components.house_duty import coordinator as coordinator_module
from custom_components.house_duty.const import (
    CONF_ABSENCE_CALENDAR,
    CONF_NOTIFICATION_TARGET,
    CONF_SPECIAL_TITLES,
)
from custom_components.house_duty.coordinator import HouseDutyCoordinator
from custom_components.house_duty.domain import Assignment, Period, RotationState


class FakeServices:
    def __init__(self) -> None:
        self.calls = []

    async def async_call(self, domain, service, data, **kwargs):
        self.calls.append((domain, service, data, kwargs))


def coordinator() -> HouseDutyCoordinator:
    value = HouseDutyCoordinator.__new__(HouseDutyCoordinator)
    value.households = [
        {"id": "a", "name": "Apartment A", CONF_NOTIFICATION_TARGET: "notify.a", CONF_ABSENCE_CALENDAR: "calendar.a"},
        {"id": "b", "name": "Apartment B", CONF_NOTIFICATION_TARGET: "notify.b", CONF_ABSENCE_CALENDAR: "calendar.b"},
    ]
    period = Period(date(2026, 8, 24))
    value.state = RotationState(period, ["a", "b"], 0, {period.start.isoformat(): Assignment(period, "b", "b")})
    value.config = {CONF_SPECIAL_TITLES: ["Gelber Sack", "Christmas trees"]}
    value.sent = set()
    value.translations = {}
    services = FakeServices()
    value.hass = SimpleNamespace(
        config=SimpleNamespace(time_zone="Europe/Berlin"),
        states=SimpleNamespace(get=lambda entity_id: object()),
        services=services,
    )
    return value


@pytest.mark.asyncio
async def test_normal_garbage_and_chore_route_to_assignee(monkeypatch) -> None:
    monkeypatch.setattr(coordinator_module.ir, "async_delete_issue", lambda *args: None)
    value = coordinator()
    await value._send_event("garbage", {"summary": "Unknown new type", "start": "2026-08-25"}, date(2026, 8, 25))
    await value._send_event("chore", {"summary": "Clean porch", "start": "2026-08-25"}, date(2026, 8, 25))
    assert [call[3]["target"]["entity_id"] for call in value.hass.services.calls] == ["notify.b", "notify.b"]


@pytest.mark.asyncio
async def test_broadcast_and_restart_deduplication(monkeypatch) -> None:
    monkeypatch.setattr(coordinator_module.ir, "async_delete_issue", lambda *args: None)
    value = coordinator()
    event = {"summary": " GELBER   SACK ", "start": "2026-08-25"}
    await value._send_event("garbage", event, date(2026, 8, 25))
    await value._send_event("garbage", event, date(2026, 8, 25))
    assert [call[3]["target"]["entity_id"] for call in value.hass.services.calls] == ["notify.a", "notify.b"]


@pytest.mark.asyncio
async def test_broadcast_retries_only_failed_recipient(monkeypatch) -> None:
    monkeypatch.setattr(coordinator_module.ir, "async_create_issue", lambda *args, **kwargs: None)
    monkeypatch.setattr(coordinator_module.ir, "async_delete_issue", lambda *args: None)
    value = coordinator()
    available = {"notify.a"}
    value.hass.states.get = lambda entity_id: object() if entity_id in available else None
    event = {"summary": "Gelber Sack", "start": "2026-08-25"}
    await value._send_event("garbage", event, date(2026, 8, 25))
    available.add("notify.b")
    await value._send_event("garbage", event, date(2026, 8, 25))
    assert [call[3]["target"]["entity_id"] for call in value.hass.services.calls] == ["notify.a", "notify.b"]


@pytest.mark.asyncio
async def test_overlapping_multiday_event_is_not_resent_as_a_new_event(monkeypatch) -> None:
    monkeypatch.setattr(coordinator_module.ir, "async_delete_issue", lambda *args: None)
    value = coordinator()

    async def events(*args):
        return [{"summary": "Holiday cleanup", "start": "2026-08-24", "end": "2026-08-27"}]

    async def save():
        return None

    value._calendar_events = events
    value._save = save
    value.config.update({"garbage_calendar": "calendar.g", "chores_calendar": "calendar.c"})
    await value._send_tomorrows_events(SimpleNamespace(date=lambda: date(2026, 8, 24)))
    assert value.hass.services.calls == []


@pytest.mark.asyncio
async def test_household_without_notification_target_is_skipped(monkeypatch) -> None:
    monkeypatch.setattr(coordinator_module.ir, "async_delete_issue", lambda *args: None)
    value = coordinator()
    value.households[1].pop(CONF_NOTIFICATION_TARGET)
    await value._send_event("garbage", {"summary": "Biomüll", "start": "2026-08-25"}, date(2026, 8, 25))
    assert value.hass.services.calls == []


@pytest.mark.asyncio
async def test_household_without_absence_calendar_is_always_available() -> None:
    value = coordinator()
    value.households[0].pop(CONF_ABSENCE_CALENDAR)
    queried = []

    async def events(entity_id, *args):
        queried.append(entity_id)
        return []

    value._calendar_events = events
    await value._async_update_next_preview()
    assert queried == ["calendar.b"]
