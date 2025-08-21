"""Fordpass Switch Entities"""
import logging

from homeassistant.components.number import NumberEntity

from custom_components.fordpass import FordPassEntity, RCC_TAGS, FordPassDataUpdateCoordinator
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY, REMOTE_START_STATE_ACTIVE
from custom_components.fordpass.const_tags import Tag, NUMBERS, ExtNumberEntityDescription
from custom_components.fordpass.fordpass_handler import UNSUPPORTED
from dataclasses import replace

from homeassistant.const import UnitOfTemperature

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Switch from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}NUMBER async_setup_entry")
    entities = []
    for a_entity_description in NUMBERS:
        a_entity_description: ExtNumberEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}NUMBER '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        entity = FordPassNumber(coordinator, a_entity_description)
        entities.append(entity)

    async_add_entities(entities, True)


class FordPassNumber(FordPassEntity, NumberEntity):
    """Define the Switch for turning ignition off/on"""

    def __init__(self, coordinator: FordPassDataUpdateCoordinator, entity_description: ExtNumberEntityDescription):
        self.translate_from_to_fahrenheit = False
        if entity_description.native_unit_of_measurement == UnitOfTemperature.CELSIUS and coordinator.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            # C * 9/5 + 32 = F
            # (F - 32) * 5/9 = C
            self.translate_from_to_fahrenheit = True
            entity_description = replace(
                entity_description,
                native_unit_of_measurement = coordinator.units.temperature_unit,
                native_step = 1,
                native_max_value = round(entity_description.native_max_value * 9/5 + 32, 0),
                native_min_value = round(entity_description.native_min_value * 9/5 + 32, 0),
            )

        super().__init__(a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)

    @property
    def extra_state_attributes(self):
        """Return sensor attributes"""
        return self._tag.get_attributes(self.coordinator.data, self.coordinator.units)

    @property
    def native_value(self):
        """Return Native Value"""
        try:
            value = self._tag.get_state(self.coordinator.data)
            if value is not None and str(value) != UNSUPPORTED:
                if self.translate_from_to_fahrenheit:
                    return round(value * 9/5 + 32, 0)
                else:
                    return value

        except ValueError:
            _LOGGER.debug(f"{self.coordinator.vli}NUMBER '{self._tag}' get_state failed with ValueError")

        return None

    async def async_set_native_value(self, value) -> None:
        try:
            if value is None or str(value) == "null" or str(value).lower() == "none":
                await self._tag.async_set_value(self.coordinator.data, self.coordinator.bridge, None)
            else:
                if self.translate_from_to_fahrenheit:
                    # we want the value in Celsius, but the user provided Fahrenheit... and we want it
                    # in steps of 0.5 °C
                    value = round(((float(value) - 32) * 5/9) * 2) / 2

                await self._tag.async_set_value(self.coordinator.data, self.coordinator.bridge, str(value))

        except ValueError:
            return None

    @property
    def available(self):
        """Return True if entity is available."""
        state = super().available
        if self._tag in RCC_TAGS:
            return state #and Tag.REMOTE_START_STATUS.get_state(self.coordinator.data) == REMOTE_START_STATE_ACTIVE
        return state
