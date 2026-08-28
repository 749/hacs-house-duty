"""Status sensors for House Duty."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseDutyCurrent(entry), HouseDutyNext(entry)])


class _Base(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry):
        self.entry = entry
        self.coordinator = entry.runtime_data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="House Duty", manufacturer="House Duty"
        )

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _name(self, household_id):
        return next((h["name"] for h in self.coordinator.households if h["id"] == household_id), None)

    def _assignment_value(self, item):
        if item is None:
            return None
        if item.household_id is None:
            key = f"component.{DOMAIN}.common.no_household_available"
            return self.coordinator.translations.get(key, "No household available")
        return self._name(item.household_id)


class HouseDutyCurrent(_Base):
    _attr_translation_key = "current_duty"

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_current"

    @property
    def native_value(self):
        return self._assignment_value(self.coordinator.current)

    @property
    def extra_state_attributes(self):
        item = self.coordinator.current
        if not item:
            return {}
        attributes = {
            "duty_period_start": item.period.start.isoformat(),
            "duty_period_end": item.period.end.isoformat(),
            "originally_next_household": self._name(item.originally_next),
            "skipped_households": [self._name(x) for x in item.skipped],
        }
        if item.problem:
            attributes["reason"] = "all_households_absent"
        return attributes


class HouseDutyNext(_Base):
    _attr_translation_key = "next_duty"

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_next"

    @property
    def native_value(self):
        return self._assignment_value(self.coordinator.next_assignment)

    @property
    def extra_state_attributes(self):
        item = self.coordinator.next_assignment
        if not item:
            return {}
        attributes = {
            "duty_period_start": item.period.start.isoformat(),
            "duty_period_end": item.period.end.isoformat(),
            "originally_next_household": self._name(item.originally_next),
            "skipped_households": [self._name(value) for value in item.skipped],
        }
        if self.coordinator.next_unavailable_calendars:
            attributes["unavailable_absence_calendars"] = self.coordinator.next_unavailable_calendars
        if item.problem:
            attributes["reason"] = "all_households_absent"
        return attributes
