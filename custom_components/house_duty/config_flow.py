"""UI configuration for House Duty."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ABSENCE_CALENDAR,
    CONF_ANCHOR_DATE,
    CONF_ANCHOR_HOUSEHOLD,
    CONF_CHORES_CALENDAR,
    CONF_GARBAGE_CALENDAR,
    CONF_HOUSEHOLDS,
    CONF_NOTIFICATION_TARGET,
    CONF_REMINDER_TIME,
    CONF_SPECIAL_TITLES,
    DEFAULT_REMINDER_TIME,
    DEFAULT_SPECIAL_TITLES,
    DOMAIN,
)
from .domain import normalized_title


def _calendar_selector():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar"))


def _notify_selector():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="notify"))


def _title_list_selector():
    return selector.TextSelector(selector.TextSelectorConfig(multiple=True))


def _clean_titles(titles: list[str]) -> list[str]:
    """Trim titles and discard empty list entries."""
    return [title.strip() for title in titles if title.strip()]


async def _async_broadcast_preview(hass, calendar: str, titles: list[str]) -> str:
    """Render the next three matching garbage events for each configured title."""
    matches: dict[str, list[str]] = {normalized_title(title): [] for title in titles}
    start = dt_util.now()
    try:
        response = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                ATTR_ENTITY_ID: calendar,
                "start_date_time": start.isoformat(),
                "end_date_time": (start + timedelta(days=366)).isoformat(),
            },
            blocking=True,
            return_response=True,
        )
        events = (response.get(calendar, {}).get("events") or []) if response else []
    except Exception:  # A preview must never prevent configuration.
        events = []
    for event in events:
        key = normalized_title(event.get("summary", ""))
        if key in matches and len(matches[key]) < 3:
            matches[key].append(str(event.get("start", "")))
    return "\n\n".join(f"**{title}**: {'; '.join(matches[normalized_title(title)]) or '—'}" for title in titles)


class HouseDutyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.households: list[dict[str, str]] = []

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            user_input[CONF_SPECIAL_TITLES] = _clean_titles(user_input[CONF_SPECIAL_TITLES])
            self.data.update(user_input)
            self._preview = await _async_broadcast_preview(
                self.hass, self.data[CONF_GARBAGE_CALENDAR], self.data[CONF_SPECIAL_TITLES]
            )
            return await self.async_step_broadcast_preview()
        schema = vol.Schema(
            {
                vol.Required(CONF_GARBAGE_CALENDAR): _calendar_selector(),
                vol.Required(CONF_CHORES_CALENDAR): _calendar_selector(),
                vol.Required(CONF_REMINDER_TIME, default=DEFAULT_REMINDER_TIME): selector.TimeSelector(),
                vol.Required(CONF_SPECIAL_TITLES, default=DEFAULT_SPECIAL_TITLES): _title_list_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_broadcast_preview(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_household()
        return self.async_show_form(
            step_id="broadcast_preview",
            data_schema=vol.Schema({}),
            description_placeholders={"preview": self._preview},
        )

    async def async_step_household(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            add_more = user_input.pop("add_another")
            self.households.append({"id": uuid4().hex, **user_input})
            if add_more:
                return await self.async_step_household()
            return await self.async_step_anchor()
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional(CONF_NOTIFICATION_TARGET): _notify_selector(),
                vol.Optional(CONF_ABSENCE_CALENDAR): _calendar_selector(),
                vol.Required("add_another", default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="household", data_schema=schema, description_placeholders={"number": str(len(self.households) + 1)}
        )

    async def async_step_anchor(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            if date.fromisoformat(user_input[CONF_ANCHOR_DATE]) > date.today():
                choices = {item["id"]: item["name"] for item in self.households}
                return self.async_show_form(
                    step_id="anchor",
                    data_schema=self._anchor_schema(choices),
                    errors={"base": "anchor_in_future"},
                )
            self.data[CONF_HOUSEHOLDS] = self.households
            self.data.update(user_input)
            return self.async_create_entry(title="House Duty", data=self.data)
        choices = {item["id"]: item["name"] for item in self.households}
        return self.async_show_form(step_id="anchor", data_schema=self._anchor_schema(choices))

    def _anchor_schema(self, choices):
        return vol.Schema(
            {
                vol.Required(CONF_ANCHOR_DATE, default=date.today().isoformat()): selector.DateSelector(),
                vol.Required(CONF_ANCHOR_HOUSEHOLD): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=k, label=v) for k, v in choices.items()]
                    )
                ),
            }
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return HouseDutyOptionsFlow()


class HouseDutyOptionsFlow(config_entries.OptionsFlowWithReload):
    """Edit general settings and the ordered household list."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "edit_household", "add_household", "remove_household", "reanchor"],
        )

    @property
    def _current(self):
        return {**self.config_entry.data, **self.config_entry.options}

    def _finish(self, updates):
        return self.async_create_entry(data={**self._current, **updates})

    def _household_select(self, key):
        return vol.Schema({vol.Required(key): self._household_selector()})

    def _household_selector(self):
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=item["id"], label=item["name"])
                    for item in self._current[CONF_HOUSEHOLDS]
                ]
            )
        )

    async def async_step_general(self, user_input=None):
        current = self._current
        if user_input is not None:
            user_input[CONF_SPECIAL_TITLES] = _clean_titles(user_input[CONF_SPECIAL_TITLES])
            order = user_input.pop("household_order")
            by_id = {item["id"]: item for item in current[CONF_HOUSEHOLDS]}
            user_input[CONF_HOUSEHOLDS] = [by_id[item_id] for item_id in order]
            self._pending_general = user_input
            self._preview = await _async_broadcast_preview(
                self.hass, user_input[CONF_GARBAGE_CALENDAR], user_input[CONF_SPECIAL_TITLES]
            )
            return await self.async_step_general_broadcast_preview()
        households = current[CONF_HOUSEHOLDS]
        schema = vol.Schema(
            {
                vol.Required(CONF_GARBAGE_CALENDAR, default=current[CONF_GARBAGE_CALENDAR]): _calendar_selector(),
                vol.Required(CONF_CHORES_CALENDAR, default=current[CONF_CHORES_CALENDAR]): _calendar_selector(),
                vol.Required(CONF_REMINDER_TIME, default=current[CONF_REMINDER_TIME]): selector.TimeSelector(),
                vol.Required(CONF_SPECIAL_TITLES, default=current[CONF_SPECIAL_TITLES]): _title_list_selector(),
                vol.Required("household_order", default=[x["id"] for x in households]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=x["id"], label=x["name"]) for x in households],
                        multiple=True,
                        sort=False,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    async def async_step_general_broadcast_preview(self, user_input=None):
        if user_input is not None:
            return self._finish(self._pending_general)
        return self.async_show_form(
            step_id="general_broadcast_preview",
            data_schema=vol.Schema({}),
            description_placeholders={"preview": self._preview},
        )

    async def async_step_edit_household(self, user_input=None):
        if user_input is not None:
            self._editing_id = user_input["household"]
            return await self.async_step_edit_household_details()
        return self.async_show_form(step_id="edit_household", data_schema=self._household_select("household"))

    async def async_step_edit_household_details(self, user_input=None):
        households = self._current[CONF_HOUSEHOLDS]
        item = next(value for value in households if value["id"] == self._editing_id)
        if user_input is not None:
            replacement = {"id": item["id"], **user_input}
            updated = [replacement if value["id"] == self._editing_id else value for value in households]
            return self._finish({CONF_HOUSEHOLDS: updated})
        schema = vol.Schema(
            {
                vol.Required("name", default=item["name"]): str,
                vol.Optional(
                    CONF_NOTIFICATION_TARGET,
                    description={"suggested_value": item.get(CONF_NOTIFICATION_TARGET)},
                ): _notify_selector(),
                vol.Optional(
                    CONF_ABSENCE_CALENDAR,
                    description={"suggested_value": item.get(CONF_ABSENCE_CALENDAR)},
                ): _calendar_selector(),
            }
        )
        return self.async_show_form(step_id="edit_household_details", data_schema=schema)

    async def async_step_add_household(self, user_input=None):
        if user_input is not None:
            item = {"id": uuid4().hex, **user_input}
            return self._finish({CONF_HOUSEHOLDS: [*self._current[CONF_HOUSEHOLDS], item]})
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional(CONF_NOTIFICATION_TARGET): _notify_selector(),
                vol.Optional(CONF_ABSENCE_CALENDAR): _calendar_selector(),
            }
        )
        return self.async_show_form(step_id="add_household", data_schema=schema)

    async def async_step_remove_household(self, user_input=None):
        current = self._current
        if user_input is not None:
            if user_input["household"] == current[CONF_ANCHOR_HOUSEHOLD]:
                return self.async_show_form(
                    step_id="remove_household",
                    data_schema=self._household_select("household"),
                    errors={"base": "anchor_household_required"},
                )
            remaining = [item for item in current[CONF_HOUSEHOLDS] if item["id"] != user_input["household"]]
            if not remaining:
                return self.async_show_form(
                    step_id="remove_household",
                    data_schema=self._household_select("household"),
                    errors={"base": "one_household_required"},
                )
            return self._finish({CONF_HOUSEHOLDS: remaining})
        return self.async_show_form(step_id="remove_household", data_schema=self._household_select("household"))

    async def async_step_reanchor(self, user_input=None):
        if user_input is not None:
            if date.fromisoformat(user_input[CONF_ANCHOR_DATE]) > date.today():
                return self.async_show_form(
                    step_id="reanchor", data_schema=self._reanchor_schema(), errors={"base": "anchor_in_future"}
                )
            return self._finish(user_input)
        return self.async_show_form(step_id="reanchor", data_schema=self._reanchor_schema())

    def _reanchor_schema(self):
        current = self._current
        return vol.Schema(
            {
                vol.Required(CONF_ANCHOR_DATE, default=current[CONF_ANCHOR_DATE]): selector.DateSelector(),
                vol.Required(CONF_ANCHOR_HOUSEHOLD, default=current[CONF_ANCHOR_HOUSEHOLD]): self._household_selector(),
            }
        )
