import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.fordpass.const import (
    DOMAIN,
    COORDINATOR_KEY,
    RCC_SEAT_MODE_HEAT_ONLY, RCC_SEAT_OPTIONS_HEAT_ONLY
)
from custom_components.fordpass.const_tags import SELECTS, ExtSelectEntityDescription, Tag, RCC_TAGS
from . import FordPassEntity, FordPassDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}SELECT async_setup_entry")

    entities = []
    for a_entity_description in SELECTS:
        a_entity_description: ExtSelectEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}SELECT '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        # me must check the supported remote climate control options seat options/mode
        if (coordinator._supports_HEATED_HEATED_SEAT_MODE == RCC_SEAT_MODE_HEAT_ONLY and
                a_entity_description.tag in [Tag.RCC_SEAT_FRONT_LEFT, Tag.RCC_SEAT_FRONT_RIGHT, Tag.RCC_SEAT_REAR_LEFT, Tag.RCC_SEAT_REAR_RIGHT]):

            # heating-only mode - so we set the corresponding icon and the heating-only options...
            a_entity_description = ExtSelectEntityDescription(
                tag=a_entity_description.tag,
                key=a_entity_description.key,
                icon="mdi:car-seat-heater",
                options=RCC_SEAT_OPTIONS_HEAT_ONLY,
                has_entity_name=a_entity_description.has_entity_name
            )

        entity = FordPassSelect(coordinator, a_entity_description)
        entities.append(entity)

    async_add_entities(entities, True)


class FordPassSelect(FordPassEntity, SelectEntity):
    def __init__(self, coordinator: FordPassDataUpdateCoordinator, entity_description: ExtSelectEntityDescription):
        super().__init__(a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)


    async def add_to_platform_finish(self) -> None:
        await super().add_to_platform_finish()

    @property
    def extra_state_attributes(self):
        return self._tag.get_attributes(self.coordinator.data, self.coordinator.units)

    @property
    def current_option(self) -> str | None:
        try:
            value = self._tag.get_state(self.coordinator.data)
            if value is None or value == "":
                return None

            if isinstance(value, (int, float)):
                value = str(value)

        except KeyError as kerr:
            _LOGGER.debug(f"SELECT KeyError: '{self._tag}' - {kerr}")
            value = None
        except TypeError as terr:
            _LOGGER.debug(f"SELECT TypeError: '{self._tag}' - {terr}")
            value = None
        return value

    async def async_select_option(self, option: str) -> None:
        try:
            if option is None or str(option) == "null" or str(option).lower() == "none":
                await self._tag.async_select_option(self.coordinator.data, self.coordinator.bridge, None)
            else:
                await self._tag.async_select_option(self.coordinator.data, self.coordinator.bridge, option)

        except ValueError:
            return None

    @property
    def available(self):
        """Return True if entity is available."""
        state = super().available
        if self._tag in RCC_TAGS:
           return state #and Tag.REMOTE_START_STATUS.get_state(self.coordinator.data) == REMOTE_START_STATE_ACTIVE
        return state