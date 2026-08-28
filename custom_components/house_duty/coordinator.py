"""Runtime coordinator for House Duty."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
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
    CONF_SPECIAL_TITLE,
    DEFAULT_REMINDER_TIME,
    DEFAULT_SPECIAL_TITLE,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .domain import (
    Absence,
    Assignment,
    Period,
    RotationState,
    configuration_preserves_rotation,
    notification_recipients,
    overlaps_period,
    period_for,
)

_LOGGER = logging.getLogger(__name__)


class HouseDutyCoordinator:
    """Reconcile assignments and deliver due calendar reminders."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = {**entry.data, **entry.options}
        self.households = self.config[CONF_HOUSEHOLDS]
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self.state: RotationState
        self.sent: set[str] = set()
        self.last_error: str | None = None
        self.listeners: list[callable] = []
        self.translations: dict[str, str] = {}
        self.next_assignment: Assignment | None = None

    async def async_initialize(self) -> None:
        self.translations = await async_get_translations(
            self.hass, self.hass.config.language, "common", integrations={DOMAIN}
        )
        raw = await self.store.async_load() or {}
        ids = [item["id"] for item in self.households]
        anchor = Period(date.fromisoformat(self.config[CONF_ANCHOR_DATE]))
        anchor_id = self.config[CONF_ANCHOR_HOUSEHOLD]
        if (
            configuration_preserves_rotation(raw.get("household_ids", []), ids)
            and raw.get("anchor") == anchor.start.isoformat()
        ):
            assignments = {
                key: Assignment(
                    Period(date.fromisoformat(key)),
                    value["household_id"],
                    value["originally_next"],
                    tuple(value["skipped"]),
                )
                for key, value in raw.get("assignments", {}).items()
            }
            self.state = RotationState(anchor, ids, int(raw.get("next_index", 0)), assignments)
            self.sent = set(raw.get("sent", []))
        else:
            if raw:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"rotation_reset_{self.entry.entry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="rotation_configuration_changed",
                )
            self.state = RotationState.from_anchor(anchor, ids, anchor_id)
        now = dt_util.now()
        await self.async_reconcile(period_for(now.date() + timedelta(days=1)))
        reminder = time.fromisoformat(self.config.get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME))
        if now.timetz().replace(tzinfo=None) >= reminder:
            await self._send_tomorrows_events(now)
        self.entry.async_on_unload(async_track_time_change(self.hass, self._async_tick, second=0))

    @callback
    def async_add_listener(self, listener) -> callable:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def _notify_listeners(self) -> None:
        for listener in self.listeners:
            listener()

    async def _calendar_events(self, entity_id: str, start: datetime, end: datetime) -> list[dict] | None:
        if self.hass.states.get(entity_id) is None:
            self.last_error = "calendar_unavailable"
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"calendar_{entity_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="calendar_unavailable",
                translation_placeholders={"entity_id": entity_id},
            )
            return None
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {ATTR_ENTITY_ID: entity_id, "start_date_time": start.isoformat(), "end_date_time": end.isoformat()},
                blocking=True,
                return_response=True,
            )
        except Exception:  # Home Assistant service errors are reported as a repair.
            _LOGGER.exception("Unable to read calendar %s", entity_id)
            self.last_error = "calendar_unavailable"
            return None
        ir.async_delete_issue(self.hass, DOMAIN, f"calendar_{entity_id}")
        return response.get(entity_id, {}).get("events", []) if response else []

    async def async_reconcile(self, through: Period) -> None:
        tz = ZoneInfo(self.hass.config.time_zone)
        unavailable: dict[str, set[str]] = {}
        cursor = self.state.anchor.start
        while cursor <= through.start:
            period = Period(cursor)
            start = datetime.combine(period.start, time.min, tz)
            end = datetime.combine(period.end, time.min, tz)
            for household in self.households:
                events = await self._calendar_events(household[CONF_ABSENCE_CALENDAR], start, end)
                if events is None:
                    self._notify_listeners()
                    return
                if any(overlaps_period(_absence(event, tz), period, tz) for event in events):
                    unavailable.setdefault(cursor.isoformat(), set()).add(household["id"])
            cursor += timedelta(days=7)
        created = self.state.reconcile(through, unavailable)
        for assignment in created:
            if assignment.problem:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"all_absent_{assignment.period.start}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="all_households_absent",
                    translation_placeholders={"date": assignment.period.start.isoformat()},
                )
                self.hass.bus.async_fire(
                    f"{DOMAIN}_assignment_problem",
                    {"period_start": assignment.period.start.isoformat(), "reason": "all_households_absent"},
                )
        await self._async_update_next_preview()
        self.last_error = None
        await self._save()
        self._notify_listeners()

    async def _async_update_next_preview(self) -> None:
        """Resolve the next duty week without consuming the persistent cursor."""
        from .domain import resolve

        current_period = period_for(dt_util.now())
        next_period = Period(current_period.start + timedelta(days=7))
        if materialized := self.state.assignments.get(next_period.start.isoformat()):
            self.next_assignment = materialized
            return
        tz = ZoneInfo(self.hass.config.time_zone)
        start = datetime.combine(next_period.start, time.min, tz)
        end = datetime.combine(next_period.end, time.min, tz)
        unavailable: set[str] = set()
        for household in self.households:
            events = await self._calendar_events(household[CONF_ABSENCE_CALENDAR], start, end)
            if events is None:
                self.next_assignment = None
                return
            if any(overlaps_period(_absence(event, tz), next_period, tz) for event in events):
                unavailable.add(household["id"])
        self.next_assignment, _ = resolve(next_period, self.state.household_ids, self.state.next_index, unavailable)

    async def _async_tick(self, now: datetime) -> None:
        local = dt_util.as_local(now)
        reminder = time.fromisoformat(self.config.get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME))
        if (local.hour, local.minute) != (reminder.hour, reminder.minute):
            return
        await self.async_reconcile(period_for(local.date() + timedelta(days=1)))
        await self._send_tomorrows_events(local)

    async def _send_tomorrows_events(self, now: datetime) -> None:
        tz = ZoneInfo(self.hass.config.time_zone)
        tomorrow = now.date() + timedelta(days=1)
        start = datetime.combine(tomorrow, time.min, tz)
        end = start + timedelta(days=1)
        for kind, calendar in (
            ("garbage", self.config[CONF_GARBAGE_CALENDAR]),
            ("chore", self.config[CONF_CHORES_CALENDAR]),
        ):
            events = await self._calendar_events(calendar, start, end)
            if events is None:
                continue
            for event in events:
                event_date = _parse_dt(event["start"], tz).date()
                if event_date != tomorrow:
                    continue
                await self._send_event(kind, event, event_date)
        await self._save()

    async def _send_event(self, kind: str, event: dict, event_date: date) -> None:
        summary = event.get("summary", "")
        uid = "|".join(
            str(part)
            for part in (
                kind,
                event.get("uid", ""),
                event.get("start"),
                event.get("end"),
                summary,
                event.get("location", ""),
                event.get("description", ""),
            )
        )
        assignment = self.state.assignments.get(period_for(event_date).start.isoformat())
        if assignment is None or assignment.problem:
            return
        recipient_ids = notification_recipients(
            kind,
            summary,
            self.config.get(CONF_SPECIAL_TITLE, DEFAULT_SPECIAL_TITLE),
            assignment.household_id,
            [item["id"] for item in self.households],
        )
        recipients = [item for item in self.households if item["id"] in recipient_ids]
        duty_name = next(item["name"] for item in self.households if item["id"] == assignment.household_id)
        for household in recipients:
            delivery_id = f"{uid}|{household['id']}"
            if delivery_id in self.sent:
                continue
            target = household[CONF_NOTIFICATION_TARGET]
            if self.hass.states.get(target) is None:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"notify_{household['id']}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="notification_unavailable",
                    translation_placeholders={"entity_id": target},
                )
                continue
            ir.async_delete_issue(self.hass, DOMAIN, f"notify_{household['id']}")
            prefix = f"component.{DOMAIN}.common"
            if kind == "garbage":
                title = self.translations.get(f"{prefix}.garbage_title", "Garbage tomorrow")
                template = self.translations.get(
                    f"{prefix}.garbage_message", "{event} is collected tomorrow. {household} is on duty."
                )
            else:
                title = self.translations.get(f"{prefix}.chore_title", "House duty tomorrow")
                template = self.translations.get(f"{prefix}.chore_message", "{household}: {event} tomorrow.")
            message = template.format(event=summary, household=duty_name)
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"message": message, "title": title},
                target={"entity_id": target},
                blocking=True,
            )
            self.sent.add(delivery_id)

    async def async_reset(self, anchor_date: date, household_id: str) -> None:
        ids = [item["id"] for item in self.households]
        self.state = RotationState.from_anchor(period_for(anchor_date), ids, household_id)
        self.sent.clear()
        await self.async_reconcile(period_for(dt_util.now()))

    async def _save(self) -> None:
        await self.store.async_save(
            {
                "anchor": self.state.anchor.start.isoformat(),
                "household_ids": self.state.household_ids,
                "next_index": self.state.next_index,
                "assignments": {
                    key: {
                        "household_id": item.household_id,
                        "originally_next": item.originally_next,
                        "skipped": list(item.skipped),
                    }
                    for key, item in self.state.assignments.items()
                },
                "sent": sorted(self.sent)[-1000:],
            }
        )

    @property
    def current(self) -> Assignment | None:
        return self.state.assignments.get(period_for(dt_util.now()).start.isoformat())


def _parse_dt(value: str, tz: ZoneInfo, *, end: bool = False) -> datetime:
    parsed = dt_util.parse_datetime(value)
    if parsed is not None:
        return parsed.astimezone(tz)
    day = date.fromisoformat(value)
    return datetime.combine(day, time.min, tz)


def _absence(event: dict, tz: ZoneInfo) -> Absence:
    return Absence(_parse_dt(event["start"], tz), _parse_dt(event["end"], tz, end=True))
