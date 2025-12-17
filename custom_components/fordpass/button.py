import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.fordpass import FordPassEntity, FordPassDataUpdateCoordinator
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY, REMOTE_START_STATE_ACTIVE
from custom_components.fordpass.const_tags import BUTTONS, Tag, ExtButtonEntityDescription

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}BUTTON async_setup_entry")
    entities = []

    for a_entity_description in BUTTONS:
        a_entity_description: ExtButtonEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}BUTTON '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        button = FordpassButton(coordinator, a_entity_description)
        entities.append(button)

    add_entity_cb(entities)


class FordpassButton(FordPassEntity, ButtonEntity):
    def __init__(self, coordinator:FordPassDataUpdateCoordinator, entity_description:ExtButtonEntityDescription):
        super().__init__(a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)

    async def async_press(self, **kwargs):
        try:
            await self._tag.async_push(self.coordinator, self.coordinator.bridge)
        except ValueError:
            return "unavailable"

    @property
    def available(self):
        """Return True if entity is available."""
        state = super().available
        if self._tag in [Tag.EV_START, Tag.EV_CANCEL, Tag.EV_PAUSE]:
            return state and Tag.EVCC_STATUS.get_state(self.coordinator.data) in ["B", "C"]
        elif self._tag == Tag.EXTEND_REMOTE_START:
            return state and Tag.REMOTE_START_STATUS.get_state(self.coordinator.data) == REMOTE_START_STATE_ACTIVE

        # elif self._tag in [Tag.MESSAGES_DELETE_LAST, Tag.MESSAGES_DELETE_ALL]:
        #     val = Tag.MESSAGES.get_state(self.coordinator.data)
        #     if val is not None and int(val) > 0:
        #         return state
        #     else:
        #         return False

        # elif self._tag == Tag.DOOR_LOCK:
        #     return state and Tag.ALARM.get_state(self.coordinator.data).upper() != "ARMED"
        # elif self._tag == Tag.DOOR_UNLOCK:
        #     return state and Tag.ALARM.get_state(self.coordinator.data).upper() != "DISARMED"

        return state