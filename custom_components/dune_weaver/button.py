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


# Pause/Resume/Stop/Skip live on the media_player (play/pause/stop/next), so
# they're not duplicated as buttons. Home isn't a media action, and Refresh
# library is a utility.
BUTTONS: tuple[DuneWeaverButtonDescription, ...] = (
    DuneWeaverButtonDescription(
        key="home",
        translation_key="home",
        press_fn=lambda coord: coord.client.home(),
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
