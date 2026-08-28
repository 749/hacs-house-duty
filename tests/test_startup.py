"""Startup ordering regression tests."""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.house_duty import coordinator as coordinator_module
from custom_components.house_duty.const import (
    CONF_ANCHOR_DATE,
    CONF_ANCHOR_HOUSEHOLD,
    CONF_HOUSEHOLDS,
    CONF_REMINDER_TIME,
)
from custom_components.house_duty.coordinator import HouseDutyCoordinator


@pytest.mark.asyncio
async def test_calendar_reconciliation_waits_until_home_assistant_started(monkeypatch) -> None:
    callbacks = []
    reconciled = []
    entry = SimpleNamespace(
        entry_id="entry",
        data={
            CONF_HOUSEHOLDS: [{"id": "a", "name": "Apartment A"}],
            CONF_ANCHOR_DATE: "2026-08-24",
            CONF_ANCHOR_HOUSEHOLD: "a",
            CONF_REMINDER_TIME: "23:00:00",
        },
        options={},
        async_on_unload=lambda callback: callbacks.append(callback),
    )
    hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    value = HouseDutyCoordinator.__new__(HouseDutyCoordinator)
    value.hass = hass
    value.entry = entry
    value.config = dict(entry.data)
    value.households = entry.data[CONF_HOUSEHOLDS]
    value.store = SimpleNamespace(async_load=lambda: _async_value(None))
    value.sent = set()
    value.last_error = None
    value.listeners = []
    value.translations = {}
    value.next_assignment = None
    value.next_unavailable_calendars = []

    monkeypatch.setattr(coordinator_module, "async_get_translations", lambda *args, **kwargs: _async_value({}))
    monkeypatch.setattr(
        coordinator_module,
        "async_at_started",
        lambda _hass, callback: callbacks.append(callback) or (lambda: None),
    )
    monkeypatch.setattr(
        coordinator_module.dt_util,
        "now",
        lambda: datetime(2026, 8, 28, 12, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    monkeypatch.setattr(coordinator_module, "async_track_time_change", lambda *args, **kwargs: lambda: None)

    async def reconcile(period):
        reconciled.append(period.start)

    value.async_reconcile = reconcile
    await value.async_initialize()
    assert reconciled == []

    await callbacks[0](hass)
    assert reconciled == [date(2026, 8, 24)]


async def _async_value(value):
    return value
