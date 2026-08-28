"""Options-flow tests for household administration."""

from types import SimpleNamespace

import pytest

from custom_components.house_duty.config_flow import HouseDutyOptionsFlow
from custom_components.house_duty.const import (
    CONF_ABSENCE_CALENDAR,
    CONF_ANCHOR_DATE,
    CONF_ANCHOR_HOUSEHOLD,
    CONF_CHORES_CALENDAR,
    CONF_GARBAGE_CALENDAR,
    CONF_HOUSEHOLDS,
    CONF_NOTIFICATION_TARGET,
    CONF_REMINDER_TIME,
    CONF_SPECIAL_TITLES,
)


class TestOptionsFlow(HouseDutyOptionsFlow):
    """Flow with a direct config entry for unit testing."""

    __test__ = False

    @property
    def config_entry(self):
        return self.entry


def flow() -> TestOptionsFlow:
    value = TestOptionsFlow()
    value.entry = SimpleNamespace(
        data={
            CONF_GARBAGE_CALENDAR: "calendar.garbage",
            CONF_CHORES_CALENDAR: "calendar.chores",
            CONF_REMINDER_TIME: "18:00:00",
            CONF_SPECIAL_TITLES: ["Gelber Sack", "Christmas trees"],
            CONF_HOUSEHOLDS: [
                {
                    "id": "a",
                    "name": "A",
                    CONF_NOTIFICATION_TARGET: "notify.a",
                    CONF_ABSENCE_CALENDAR: "calendar.a",
                },
                {
                    "id": "b",
                    "name": "B",
                    CONF_NOTIFICATION_TARGET: "notify.b",
                    CONF_ABSENCE_CALENDAR: "calendar.b",
                },
            ],
            CONF_ANCHOR_DATE: "2026-01-05",
            CONF_ANCHOR_HOUSEHOLD: "a",
        },
        options={},
    )
    return value


@pytest.mark.asyncio
async def test_every_options_operation_has_a_native_form() -> None:
    value = flow()
    assert (await value.async_step_init())["type"] == "menu"
    for step in (
        value.async_step_general,
        value.async_step_edit_household,
        value.async_step_add_household,
        value.async_step_remove_household,
        value.async_step_reanchor,
    ):
        assert (await step())["type"] == "form"


@pytest.mark.asyncio
async def test_edit_preserves_stable_household_identity() -> None:
    value = flow()
    await value.async_step_edit_household({"household": "b"})
    result = await value.async_step_edit_household_details(
        {"name": "Renamed", CONF_NOTIFICATION_TARGET: "notify.new", CONF_ABSENCE_CALENDAR: "calendar.new"}
    )
    edited = result["data"][CONF_HOUSEHOLDS][1]
    assert edited == {
        "id": "b",
        "name": "Renamed",
        CONF_NOTIFICATION_TARGET: "notify.new",
        CONF_ABSENCE_CALENDAR: "calendar.new",
    }


@pytest.mark.asyncio
async def test_anchor_household_cannot_be_removed() -> None:
    value = flow()
    result = await value.async_step_remove_household({"household": "a"})
    assert result["errors"] == {"base": "anchor_household_required"}


@pytest.mark.asyncio
async def test_household_optional_entities_can_be_cleared() -> None:
    value = flow()
    await value.async_step_edit_household({"household": "b"})
    result = await value.async_step_edit_household_details({"name": "No entities"})
    edited = result["data"][CONF_HOUSEHOLDS][1]
    assert edited == {"id": "b", "name": "No entities"}
