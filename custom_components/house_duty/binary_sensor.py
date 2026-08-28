"""Problem status for House Duty."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HouseDutyProblem(entry)])


class HouseDutyProblem(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry):
        self.coordinator = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_problem"

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def is_on(self):
        return self.coordinator.last_error is not None or bool(
            self.coordinator.current and self.coordinator.current.problem
        )

    @property
    def extra_state_attributes(self):
        return {"reason": self.coordinator.last_error or ("all_households_absent" if self.is_on else None)}
