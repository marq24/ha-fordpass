import asyncio
import logging

from datetime import datetime
from homeassistant.components.image import ImageEntity, Image, ImageContentTypeError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FordPassDataUpdateCoordinator, Tag, COORDINATOR_KEY, MANUFACTURER_LINCOLN, MANUFACTURER_FORD
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the vehicle image entity from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]

    # Add the static image entity
    async_add_entities([VehicleImageEntity(hass, coordinator)])

class VehicleImageEntity(ImageEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, coordinator:FordPassDataUpdateCoordinator):
        # Pass hass to the parent ImageEntity so it sets up access tokens correctly
        super().__init__(hass)
        self.coordinator = coordinator
        self._image_lock = asyncio.Lock()
        self._tag = Tag.VEHICLE_IMAGE
        self._attr_translation_key = self._tag.key.lower()
        self.entity_id = f"{Platform.IMAGE}.fordpass_{self.coordinator._vin.lower()}_{self._tag.key}".lower()

        self._img_data = None
        self._img_type = None
        self.image_last_updated = datetime.now()

    @property
    def device_id(self):
        return f"fordpass_did_{self.self.coordinator._vin.lower()}"

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return f"fordpass_uid_{self.coordinator._vin}_{self._tag.key}".lower()

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self.coordinator._vin)},
            "name": f"VIN: {self.coordinator._vin}",
            "manufacturer": MANUFACTURER_LINCOLN if self.coordinator._is_brand_lincoln else MANUFACTURER_FORD,
        }

    @property
    def image_url(self) -> str | None:
        """Return the static vehicle image URL."""
        if self.coordinator.data:
            return self._tag.get_state(self.coordinator.data, None)
        return None

    async def _async_load_image_from_url(self, url: str) -> Image | None:
        """Load an image by url."""
        _LOGGER.debug(f"_async_load_image_from_url(): '{url}'")
        async with self._image_lock:
            try:
                if self._img_data is None:
                    self._img_type, self._img_data = await self.coordinator.async_get_vehicle_image_bytes(a_url=self._tag.get_state(self.coordinator.data, None))

                return Image(
                    content=self._img_data,
                    content_type=self._img_type,
                )
            except ImageContentTypeError:
                _LOGGER.info(f"_async_load_image_from_url(): {self.entity_id}: Image from {url} has invalid content type: {self._img_type}")
            except BaseException as ex:
                _LOGGER.info(f"_async_load_image_from_url(): Exception {type(ex).__name__} - {ex}")

        return None
