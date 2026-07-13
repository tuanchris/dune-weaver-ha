"""Action buttons: home, stop, pause, resume, skip pattern.

All of these hit the /sand_* one-shot HTTP routes (or fire-and-forget commands),
which only *signal* the firmware main loop — the safe way to start motion over
HTTP on this firmware.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity


@dataclass(frozen=True, kw_only=True)
class DuneWeaverButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[DuneWeaverCoordinator], Awaitable[None]]


BUTTONS: tuple[DuneWeaverButtonDescription, ...] = (
    DuneWeaverButtonDescription(
        key="home",
        translation_key="home",
        press_fn=lambda coord: coord.client.home(),
    ),
    DuneWeaverButtonDescription(
        key="stop",
        translation_key="stop",
        press_fn=lambda coord: coord.client.stop(),
    ),
    DuneWeaverButtonDescription(
        key="pause",
        translation_key="pause",
        press_fn=lambda coord: coord.client.pause(),
    ),
    DuneWeaverButtonDescription(
        key="resume",
        translation_key="resume",
        press_fn=lambda coord: coord.client.resume(),
    ),
    DuneWeaverButtonDescription(
        key="skip",
        translation_key="skip_pattern",
        press_fn=lambda coord: coord.client.playlist_skip(),
    ),
    DuneWeaverButtonDescription(
        key="stop_playlist",
        translation_key="stop_playlist",
        press_fn=lambda coord: coord.async_stop_playlist(),
    ),
    DuneWeaverButtonDescription(
        key="refresh_library",
        translation_key="refresh_library",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda coord: coord.async_refresh_library(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DuneWeaverButton(coordinator, description) for description in BUTTONS
    )


class DuneWeaverButton(DuneWeaverEntity, ButtonEntity):
    entity_description: DuneWeaverButtonDescription

    def __init__(
        self,
        coordinator: DuneWeaverCoordinator,
        description: DuneWeaverButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
        await self.coordinator.async_request_refresh()
