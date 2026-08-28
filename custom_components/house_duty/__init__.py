"""House Duty integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import HouseDutyCoordinator

type HouseDutyConfigEntry = ConfigEntry[HouseDutyCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HouseDutyConfigEntry) -> bool:
    coordinator = HouseDutyCoordinator(hass, entry)
    await coordinator.async_initialize()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.services.has_service(DOMAIN, "reset_rotation"):

        async def reset_rotation(call):
            target = hass.config_entries.async_get_entry(call.data["config_entry_id"])
            if target and target.runtime_data:
                from datetime import date

                await target.runtime_data.async_reset(
                    date.fromisoformat(call.data["anchor_date"]), call.data["household_id"]
                )

        hass.services.async_register(
            DOMAIN,
            "reset_rotation",
            reset_rotation,
            schema=vol.Schema(
                {
                    vol.Required("config_entry_id"): str,
                    vol.Required("anchor_date"): str,
                    vol.Required("household_id"): str,
                }
            ),
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HouseDutyConfigEntry) -> bool:
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if result and len(hass.config_entries.async_entries(DOMAIN)) <= 1:
        hass.services.async_remove(DOMAIN, "reset_rotation")
    return result
