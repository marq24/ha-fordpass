import asyncio
import logging
from pathlib import Path
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

    def __init__(self, hass: HomeAssistant, coordinator: FordPassDataUpdateCoordinator):
        # Pass hass to the parent ImageEntity so it sets up access tokens correctly
        super().__init__(hass)
        self.coordinator = coordinator
        self.vin_lower = self.coordinator._vin.lower()
        self._image_lock = asyncio.Lock()
        self._tag = Tag.VEHICLE_IMAGE
        self._attr_translation_key = self._tag.key.lower()
        self.entity_id = f"{Platform.IMAGE}.fordpass_{self.vin_lower}_{self._tag.key}".lower()

        self._img_data = None
        self._img_type = None
        self.image_last_updated = datetime.now()

        # Define persistent local storage paths in the Home Assistant config directory
        base_path = Path(hass.config.path("fordpass-data"))
        self._image_path = base_path / f"vehicle_image_{self.vin_lower}.jpg" # Extension will adapt/serve bytes regardless, but keep generic
        self._type_path = base_path / f"vehicle_image_{self.vin_lower}.type"

    @property
    def device_id(self):
        return f"fordpass_did_{self.vin_lower}"

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return f"fordpass_uid_{self.coordinator._vin}_{self._tag.key}".lower()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this device."""
        return self.coordinator.gen_device_info

    @property
    def image_url(self) -> str | None:
        """Return the static vehicle image URL."""
        if self.coordinator.data:
            return self._tag.get_state(self.coordinator.data, None)
        return None

    async def _async_load_image_from_url(self, url: str) -> Image | None:
        """Load an image by url or fallback to permanent local storage."""
        _LOGGER.debug(f"_async_load_image_from_url(): called with '{url}'")
        async with self._image_lock:
            try:
                # 1. Check in-memory cache first
                if self._img_data is None or self._img_type is None:
                    # 2. Check if both the image file and content-type metadata exist locally on disk
                    file_exists = await self.hass.async_add_executor_job(
                        lambda: self._image_path.exists() and self._type_path.exists()
                    )

                    if file_exists:
                        _LOGGER.debug(f"_async_load_image_from_url(): loading vehicle image and type from local storage: {self._image_path}")
                        def _load_local():
                            img_bytes = self._image_path.read_bytes()
                            img_type = self._type_path.read_text(encoding="utf-8").strip()
                            return img_bytes, img_type

                        self._img_data, self._img_type = await self.hass.async_add_executor_job(_load_local)
                    else:
                        # 3. Fetch from coordinator if not available locally
                        url_to_fetch = self._tag.get_state(self.coordinator.data, None)
                        if url_to_fetch:
                            self._img_type, self._img_data = await self.coordinator.async_get_vehicle_image_bytes(a_url=url_to_fetch)

                            # Save permanently to disk along with its actual content type
                            if self._img_data and self._img_type:
                                def _save_local():
                                    self._image_path.parent.mkdir(parents=True, exist_ok=True)
                                    self._image_path.write_bytes(self._img_data)
                                    self._type_path.write_text(self._img_type, encoding="utf-8")

                                await self.hass.async_add_executor_job(_save_local)
                                _LOGGER.debug(f"_async_load_image_from_url(): saved vehicle image and type to local storage: {self._image_path}")

                if self._img_data and self._img_type:
                    return Image(
                        content=self._img_data,
                        content_type=self._img_type,
                    )
            except ImageContentTypeError:
                _LOGGER.info(f"_async_load_image_from_url(): image from {url} has invalid content type: {self._img_type}")
            except Exception as ex:
                _LOGGER.info(f"_async_load_image_from_url(): Exception {type(ex).__name__}: {ex}")

        return None