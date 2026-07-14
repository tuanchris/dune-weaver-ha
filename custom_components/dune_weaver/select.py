"""LED select entities: palette, ball direction/background, and the machine-state
effect hooks. Current values come from /sand_settings (merged into the
coordinator data); writes go through the live /sand_led path or $LED/* commands.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CLEAR_MODES,
    LED_BALL_BG_OPTIONS,
    LED_DIRECTIONS,
    LED_HOOK_OPTIONS,
    LED_PALETTES,
)
from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity

SERVICE_RUN_PATTERN = "run_pattern"
SERVICE_RUN_PLAYLIST = "run_playlist"


def _strip_txt(name: str) -> str:
    return name[:-4] if name.lower().endswith(".txt") else name


def _current_pattern(data: dict[str, Any]) -> str | None:
    """The running pattern normalized to a /sand_patterns key (relative to
    /patterns), or None when nothing is running."""
    if not data.get("running"):
        return None
    file = data.get("file") or ""
    for prefix in ("/sd/patterns/", "/patterns/", "sd/patterns/", "patterns/"):
        if file.startswith(prefix):
            file = file[len(prefix) :]
            break
    return file or None


def _current_playlist(data: dict[str, Any]) -> str | None:
    playlist = data.get("playlist") or {}
    if not playlist.get("active"):
        return None
    name = playlist.get("name") or ""
    return _strip_txt(name) or None


@dataclass(frozen=True, kw_only=True)
class DuneWeaverSelectDescription(SelectEntityDescription):
    setting_key: str  # key in /sand_settings, e.g. "LED/Palette"
    select_fn: Callable[[DuneWeaverCoordinator, str], Awaitable[None]]


@dataclass(frozen=True, kw_only=True)
class DuneWeaverLibrarySelectDescription(SelectEntityDescription):
    options_key: str  # key in coordinator data holding the option list
    current_fn: Callable[[dict[str, Any]], str | None]
    run_fn: Callable[[DuneWeaverCoordinator, str], Awaitable[None]]
    strip_txt: bool = False


# Pattern / playlist pickers — options come from the cached catalogs; selecting
# one starts it on the table.
LIBRARY_SELECTS: tuple[DuneWeaverLibrarySelectDescription, ...] = (
    DuneWeaverLibrarySelectDescription(
        key="pattern",
        translation_key="pattern",
        options_key="patterns",
        current_fn=_current_pattern,
        run_fn=lambda coord, opt: coord.async_run_pattern(opt),
    ),
    DuneWeaverLibrarySelectDescription(
        key="playlist",
        translation_key="playlist",
        options_key="playlists",
        current_fn=_current_playlist,
        run_fn=lambda coord, opt: coord.async_run_playlist(opt),
        strip_txt=True,
    ),
)


SELECTS: tuple[DuneWeaverSelectDescription, ...] = (
    DuneWeaverSelectDescription(
        key="led_palette",
        translation_key="led_palette",
        entity_category=EntityCategory.CONFIG,
        options=LED_PALETTES,
        setting_key="LED/Palette",
        select_fn=lambda coord, opt: coord.async_write_led(palette=opt),
    ),
    DuneWeaverSelectDescription(
        key="led_direction",
        translation_key="led_direction",
        entity_category=EntityCategory.CONFIG,
        options=LED_DIRECTIONS,
        setting_key="LED/Direction",
        select_fn=lambda coord, opt: coord.async_write_led(direction=opt),
    ),
    DuneWeaverSelectDescription(
        key="led_ball_background",
        translation_key="led_ball_background",
        entity_category=EntityCategory.CONFIG,
        options=LED_BALL_BG_OPTIONS,
        setting_key="LED/BallBg",
        select_fn=lambda coord, opt: coord.async_write_led(bg=opt),
    ),
    DuneWeaverSelectDescription(
        key="led_run_effect",
        translation_key="led_run_effect",
        entity_category=EntityCategory.CONFIG,
        options=LED_HOOK_OPTIONS,
        setting_key="LED/RunEffect",
        select_fn=lambda coord, opt: coord.async_set_led_hook("RunEffect", opt),
    ),
    DuneWeaverSelectDescription(
        key="led_idle_effect",
        translation_key="led_idle_effect",
        entity_category=EntityCategory.CONFIG,
        options=LED_HOOK_OPTIONS,
        setting_key="LED/IdleEffect",
        select_fn=lambda coord, opt: coord.async_set_led_hook("IdleEffect", opt),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_RUN_PATTERN,
        {
            vol.Required("pattern"): cv.string,
            vol.Optional("clear", default="none"): vol.In(CLEAR_MODES),
        },
        "async_run_pattern_service",
    )
    platform.async_register_entity_service(
        SERVICE_RUN_PLAYLIST,
        {vol.Required("playlist"): cv.string},
        "async_run_playlist_service",
    )
    entities: list[SelectEntity] = [
        DuneWeaverLibrarySelect(coordinator, description)
        for description in LIBRARY_SELECTS
    ]
    if "led" in coordinator.data:
        entities += [
            DuneWeaverSelect(coordinator, description) for description in SELECTS
        ]
    async_add_entities(entities)


class _RunServiceMixin:
    """Adds the run_pattern / run_playlist services to any Dune Weaver select,
    so either the pattern or playlist picker is a valid target."""

    coordinator: DuneWeaverCoordinator

    async def async_run_pattern_service(
        self, pattern: str, clear: str = "none"
    ) -> None:
        await self.coordinator.async_run_pattern(pattern, clear)

    async def async_run_playlist_service(self, playlist: str) -> None:
        await self.coordinator.async_run_playlist(playlist)


class DuneWeaverSelect(_RunServiceMixin, DuneWeaverEntity, SelectEntity):
    entity_description: DuneWeaverSelectDescription

    def __init__(
        self,
        coordinator: DuneWeaverCoordinator,
        description: DuneWeaverSelectDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def current_option(self) -> str | None:
        value = (self.coordinator.data.get("settings") or {}).get(
            self.entity_description.setting_key
        )
        # Only surface a value the firmware actually reported and we can render.
        return value if value in self.entity_description.options else None

    async def async_select_option(self, option: str) -> None:
        await self.entity_description.select_fn(self.coordinator, option)


class DuneWeaverLibrarySelect(_RunServiceMixin, DuneWeaverEntity, SelectEntity):
    """Pattern/playlist picker whose options are the cached table catalog."""

    entity_description: DuneWeaverLibrarySelectDescription

    def __init__(
        self,
        coordinator: DuneWeaverCoordinator,
        description: DuneWeaverLibrarySelectDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def options(self) -> list[str]:
        raw = self.coordinator.data.get(self.entity_description.options_key) or []
        if self.entity_description.strip_txt:
            return [_strip_txt(item) for item in raw]
        return list(raw)

    @property
    def current_option(self) -> str | None:
        current = self.entity_description.current_fn(self.coordinator.data)
        # HA warns if current_option isn't one of the options; only report a
        # match (the running file may be a subfolder pattern not in the list).
        return current if current in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.entity_description.run_fn(self.coordinator, option)
