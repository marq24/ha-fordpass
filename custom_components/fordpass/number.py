"""Fordpass Switch Entities"""
import logging
from dataclasses import replace
from numbers import Number

from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTemperature

from custom_components.fordpass import FordPassEntity, RCC_TAGS, FordPassDataUpdateCoordinator
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY
from custom_components.fordpass.const_tags import Tag, NUMBERS, ExtNumberEntityDescription
from custom_components.fordpass.fordpass_handler import UNSUPPORTED, ROOT_METRICS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Switch from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}NUMBER async_setup_entry")
    entities = []
    check_data_availability = coordinator.data is not None and len(coordinator.data.get(ROOT_METRICS, {})) > 0

    for a_entity_description in NUMBERS:
        a_entity_description: ExtNumberEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}NUMBER '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        entity = FordPassNumber(coordinator, a_entity_description)
        if a_entity_description.skip_existence_check or not check_data_availability:
            entities.append(entity)
        else:
            # calling the state reading function to check if the entity should be added (if there is any data)
            value = a_entity_description.tag.state_fn(coordinator.data)
            if value is not None and ((isinstance(value, (str, Number)) and str(value) != UNSUPPORTED) or
                                      (isinstance(value, (dict, list)) and len(value) != 0) ):
                entities.append(entity)
            else:
                _LOGGER.debug(f"{coordinator.vli}NUMBER '{a_entity_description.tag}' skipping cause no data available: type: {type(value).__name__} - value:'{value}'")

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
                native_unit_of_measurement=coordinator.units.temperature_unit,
                native_step=1,
                native_max_value=round(entity_description.native_max_value * 1.8 + 32, 0),
                native_min_value=round(entity_description.native_min_value * 1.8 + 32, 0)
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
                if self._tag == Tag.RCC_TEMPERATURE:
                    # the latest fordPass App also support "HI" and "LO"
                    # as 'valid' values for the remote temperature...
                    # which sucks some sort of - since we must MAP this
                    # to our number Field
                    if str(value).upper() == "HI":
                        value = 30.5
                    elif str(value).upper() == "LO":
                        value = 15.5

                    if self.translate_from_to_fahrenheit:
                        value = round(value * 1.8 + 32, 0)

            return value

        except ValueError:
            _LOGGER.debug(f"{self.coordinator.vli}NUMBER '{self._tag}' native_value() [or internal get_state()] failed with ValueError")

        return None

    async def async_set_native_value(self, value) -> None:
        try:
            if value is None or str(value) == "null" or str(value).lower() == "none":
                await self._tag.async_set_value(self.coordinator.data, self.coordinator.bridge, None)
            else:
                if self._tag == Tag.RCC_TEMPERATURE:
                    if self.translate_from_to_fahrenheit:
                        # we want the value in Celsius, but the user provided Fahrenheit... and we want it
                        # in steps of 0.5 °C
                        value = round(((float(value) - 32) / 1.8) * 2, 0) / 2

                    # we use 15.5°C as LO and 30.5°C as HI
                    if value < 16:
                        value = "LO"
                    elif value > 30:
                        value = "HI"

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
