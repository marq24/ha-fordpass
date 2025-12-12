import logging
from dataclasses import replace
from numbers import Number

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.fordpass.const import (
    DOMAIN,
    COORDINATOR_KEY,
    RCC_SEAT_MODE_HEAT_ONLY, RCC_SEAT_OPTIONS_HEAT_ONLY, RCC_TEMPERATURES_CELSIUS
)
from custom_components.fordpass.const_tags import SELECTS, ExtSelectEntityDescription, Tag, RCC_TAGS
from . import FordPassEntity, FordPassDataUpdateCoordinator, UNSUPPORTED, FordpassDataHandler, ROOT_METRICS

_LOGGER = logging.getLogger(__name__)

ELVEH_TARGET_CHARGE_TAG_TO_INDEX = {
    Tag.ELVEH_TARGET_CHARGE: 0,
    Tag.ELVEH_TARGET_CHARGE_ALT1: 1,
    Tag.ELVEH_TARGET_CHARGE_ALT2: 2
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}SELECT async_setup_entry")

    entities = []
    check_data_availability = coordinator.data is not None and len(coordinator.data.get(ROOT_METRICS, {})) > 0
    for a_entity_description in SELECTS:
        a_entity_description: ExtSelectEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}SELECT '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        # me must check the supported remote climate control options seat options/mode
        if (coordinator._supports_HEATED_HEATED_SEAT_MODE == RCC_SEAT_MODE_HEAT_ONLY and
                a_entity_description.tag in [Tag.RCC_SEAT_FRONT_LEFT, Tag.RCC_SEAT_FRONT_RIGHT, Tag.RCC_SEAT_REAR_LEFT, Tag.RCC_SEAT_REAR_RIGHT]):

            # heating-only mode - so we set the corresponding icon and the heating-only options...
            a_entity_description = replace(
                a_entity_description,
                icon="mdi:car-seat-heater",
                options=RCC_SEAT_OPTIONS_HEAT_ONLY
            )

        # special handling for the ELVEH_TARGET_CHARGE tags [where we have to add the location name]
        if a_entity_description.tag in ELVEH_TARGET_CHARGE_TAG_TO_INDEX.keys():
            if FordpassDataHandler.is_elev_target_charge_supported(coordinator.data, ELVEH_TARGET_CHARGE_TAG_TO_INDEX[a_entity_description.tag]):
                a_location_name = FordpassDataHandler.get_elev_target_charge_name(coordinator.data, ELVEH_TARGET_CHARGE_TAG_TO_INDEX[a_entity_description.tag])
                if a_location_name is not UNSUPPORTED:
                    a_entity_description = replace(
                        a_entity_description,
                        name_addon=f"{a_location_name}:"
                    )
            else:
                _LOGGER.debug(f"{coordinator.vli}SELECT '{a_entity_description.tag}' not supported/no valid data present")
                continue

        entity = FordPassSelect(coordinator, a_entity_description)
        if a_entity_description.skip_existence_check or not check_data_availability:
            entities.append(entity)
        else:
            # calling the state reading function to check if the entity should be added (if there is any data)
            value = a_entity_description.tag.state_fn(coordinator.data)
            if value is not None and ((isinstance(value, (str, Number)) and str(value) != UNSUPPORTED) or
                                      (isinstance(value, (dict, list)) and len(value) != 0) ):
                entities.append(entity)
            else:
                _LOGGER.debug(f"{coordinator.vli}SELECT '{a_entity_description.tag}' skipping cause no data available: type: {type(value).__name__} - value:'{value}'")

    async_add_entities(entities, True)


class FordPassSelect(FordPassEntity, SelectEntity):
    def __init__(self, coordinator: FordPassDataUpdateCoordinator, entity_description: ExtSelectEntityDescription):
        super().__init__(a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)


    async def add_to_platform_finish(self) -> None:
        if self._tag == Tag.RCC_TEMPERATURE:
            has_pf_data = hasattr(self.platform, "platform_data")
            has_pf_trans = hasattr(self.platform.platform_data, "platform_translations") if has_pf_data else hasattr(self.platform, "platform_translations")
            has_pf_default_lang_trans = hasattr(self.platform.platform_data, "default_language_platform_translations") if has_pf_data else hasattr(self.platform, "default_language_platform_translations")

            for a_key in RCC_TEMPERATURES_CELSIUS:
                a_trans_key = f"component.{DOMAIN}.entity.select.{Tag.RCC_TEMPERATURE.key.lower()}.state.{a_key.lower()}"

                if a_key.lower() == "hi":
                    a_value = "☀|MAX"
                elif a_key.lower() == "lo":
                    a_value = "❄|MIN"
                else:
                    a_temperature = float(a_key.replace('_', '.'))
                    if self.coordinator.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
                        # C * 9/5 + 32 = F
                        a_temperature = a_temperature * 1.8 + 32
                        a_value = f"{a_temperature:.1f} °F"
                    else:
                        a_value = f"{a_temperature:.1f} °C"

                if has_pf_data:
                    if has_pf_trans:
                        self.platform.platform_data.platform_translations[a_trans_key] = a_value
                    if has_pf_default_lang_trans:
                        self.platform.platform_data.default_language_platform_translations[a_trans_key] = a_value
                else:
                    # old HA compatible version...
                    if has_pf_trans:
                        self.platform.platform_translations[a_trans_key] = a_value
                    if has_pf_default_lang_trans:
                        self.platform.default_language_platform_translations[a_trans_key] = a_value

        await super().add_to_platform_finish()

    @property
    def extra_state_attributes(self):
        return self._tag.get_attributes(self.coordinator.data, self.coordinator.units)

    @property
    def current_option(self) -> str | None:
        try:
            value = self._tag.get_state(self.coordinator.data)
            if value is None or value == "" or str(value).lower() == "null" or str(value).lower() == "none":
                return None

            if isinstance(value, (int, float)):
                value = str(value)

            if self._tag == Tag.RCC_TEMPERATURE:
                # our option keys are all lower case...
                value = str(value).lower()
                # our option keys have _ instead of .
                value = value.replace('.', '_')
                # the full numbers of our option keys are just the plain number (no '_0' suffix)
                value = value.replace('_0', '')

        except KeyError as kerr:
            _LOGGER.debug(f"SELECT KeyError: '{self._tag}' - {kerr}")
            value = None
        except TypeError as terr:
            _LOGGER.debug(f"SELECT TypeError: '{self._tag}' - {terr}")
            value = None
        return value

    async def async_select_option(self, option: str) -> None:
        try:
            if option is None or option=="" or str(option).lower() == "null" or str(option).lower() == "none":
                await self._tag.async_select_option(self.coordinator.data, self.coordinator.bridge, None)
            else:
                if self._tag == Tag.RCC_TEMPERATURE:
                    option = option.upper()
                await self._tag.async_select_option(self.coordinator.data, self.coordinator.bridge, option)

        except ValueError:
            return None

    @property
    def available(self):
        """Return True if entity is available."""
        if self.current_option == UNSUPPORTED:
            return False

        state = super().available
        if self._tag in RCC_TAGS:
           return state #and Tag.REMOTE_START_STATUS.get_state(self.coordinator.data) == REMOTE_START_STATE_ACTIVE
        return state