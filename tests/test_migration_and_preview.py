"""Configuration migration and broadcast preview tests."""

from types import SimpleNamespace

import pytest

from custom_components.house_duty import async_migrate_entry
from custom_components.house_duty.config_flow import _async_broadcast_preview
from custom_components.house_duty.const import CONF_SPECIAL_TITLE, CONF_SPECIAL_TITLES


@pytest.mark.asyncio
async def test_version_one_single_title_migrates_to_list() -> None:
    entry = SimpleNamespace(
        version=1,
        data={CONF_SPECIAL_TITLE: "Gelber Sack", "other": True},
        options={CONF_SPECIAL_TITLE: "Christmas trees"},
    )
    updated = {}

    def update_entry(config_entry, **changes):
        updated.update(changes)

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update_entry))
    assert await async_migrate_entry(hass, entry)
    assert updated["version"] == 2
    assert updated["data"][CONF_SPECIAL_TITLES] == ["Gelber Sack"]
    assert updated["options"][CONF_SPECIAL_TITLES] == ["Christmas trees"]
    assert CONF_SPECIAL_TITLE not in updated["data"]


@pytest.mark.asyncio
async def test_preview_lists_next_three_matches_per_title() -> None:
    events = [{"summary": "Gelber Sack", "start": f"2026-09-0{day}"} for day in range(1, 5)] + [
        {"summary": " CHRISTMAS trees ", "start": "2026-12-20"}
    ]

    async def async_call(*args, **kwargs):
        return {"calendar.garbage": {"events": events}}

    hass = SimpleNamespace(services=SimpleNamespace(async_call=async_call))
    preview = await _async_broadcast_preview(
        hass, "calendar.garbage", ["Gelber Sack", "Christmas trees", "Unscheduled"]
    )
    assert "2026-09-01; 2026-09-02; 2026-09-03" in preview
    assert "2026-09-04" not in preview
    assert "**Christmas trees**: 2026-12-20" in preview
    assert "**Unscheduled**: —" in preview
