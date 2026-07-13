"""LED select entities: palette, ball direction/background, and the machine-state
effect hooks. Current values come from /sand_settings (merged into the
coordinator data); writes go through the live /sand_led path or $LED/* commands.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    LED_BALL_BG_OPTIONS,
    LED_DIRECTIONS,
    LED_HOOK_OPTIONS,
    LED_PALETTES,
)
from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity


@dataclass(frozen=True, kw_only=True)
class DuneWeaverSelectDescription(SelectEntityDescription):
    setting_key: str  # key in /sand_settings, e.g. "LED/Palette"
    select_fn: Callable[[DuneWeaverCoordinator, str], Awaitable[None]]


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
    if "led" not in coordinator.data:
        return
    async_add_entities(
        DuneWeaverSelect(coordinator, description) for description in SELECTS
    )


class DuneWeaverSelect(DuneWeaverEntity, SelectEntity):
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
