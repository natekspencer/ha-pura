"""Support for Pura fragrance slots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import functools

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PuraConfigEntry
from .const import DOMAIN
from .coordinator import PuraDataUpdateCoordinator
from .entity import PuraEntity
from .helpers import get_device_id, has_fragrance, parse_intensity

INTENSITY_MAP = {"subtle": 3, "medium": 6, "strong": 10}


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura selects using config entry."""
    coordinator: PuraDataUpdateCoordinator = entry.runtime_data

    entities = [
        PuraSelectEntity(
            coordinator=coordinator,
            description=description,
            device_type=device_type,
            device_id=get_device_id(device),
        )
        for device_types, descriptions in SELECT_DESCRIPTIONS.items()
        for device_type, devices in coordinator.devices.items()
        if device_type in device_types
        for device in devices
        for description in descriptions
    ]

    if not entities:
        return

    async_add_entities(entities)


@dataclass(kw_only=True)
class PuraSelectEntityDescription(SelectEntityDescription):
    """Pura select entity description."""

    current_fn: Callable[[dict], str]
    options_fn: Callable[[dict], list[str]] | None = None
    select_fn: Callable[[PuraSelectEntity, str], functools.partial[bool]]


SELECT_DESCRIPTIONS = {
    ("wall", "plus", "mini"): (
        PuraSelectEntityDescription(
            key="fragrance",
            translation_key="fragrance",
            current_fn=lambda data: "off" if (b := data["bay"]) == 0 else f"slot_{b}",
            options_fn=lambda data: (
                ["off"] + [f"slot_{i}" for i in (1, 2) if has_fragrance(data, i)]
            ),
            select_fn=lambda select, option: functools.partial(
                select.coordinator.api.set_always_on,
                select._device_id,
                bay=int(option.replace("slot_", "")),
            ),
        ),
        PuraSelectEntityDescription(
            key="intensity",
            translation_key="intensity",
            entity_category=EntityCategory.CONFIG,
            current_fn=lambda data: parse_intensity(data["intensity"]),
            options=["off", "subtle", "medium", "strong"],
            select_fn=lambda select, option: functools.partial(
                select.coordinator.api.set_intensity,
                select._device_id,
                bay=select._intensity_data["bay"],
                controller=(
                    str(select._intensity_data["number"])
                    if (controller := select._intensity_data["controller"])
                    == "schedule"
                    else controller
                ),
                intensity=INTENSITY_MAP[option],
            ),
        ),
    ),
}


class PuraSelectEntity(PuraEntity, SelectEntity):
    """Pura select."""

    entity_description: PuraSelectEntityDescription

    @property
    def current_option(self) -> str:
        """Return the selected entity option to represent the entity state."""
        return self.entity_description.current_fn(self._intensity_data)

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        if options_fn := self.entity_description.options_fn:
            return options_fn(self.get_device())
        return super().options

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option == "off":
            job = functools.partial(self.coordinator.api.stop_all, self._device_id)
        elif self.get_device()["controller"] == "away":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="away_mode_active"
            )
        else:
            job = self.entity_description.select_fn(self, option)
            if not job.keywords["bay"]:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="no_active_fragrance"
                )

        if await self.hass.async_add_executor_job(job):
            await self.coordinator.async_request_refresh()
