"""Number entities: table feed speed and the LED animation/ball parameters.

Feed values come from /sand_status; the LED knobs come from /sand_settings
(the coordinator merges them under data["settings"]). All are applied live.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity


@dataclass(frozen=True, kw_only=True)
class DuneWeaverNumberDescription(NumberEntityDescription):
    value_fn: Callable[[dict[str, Any]], float | None]
    set_fn: Callable[[DuneWeaverCoordinator, float], Awaitable[None]]


def _led_setting(key: str) -> Callable[[dict[str, Any]], float | None]:
    """Read an integer LED setting (a string in /sand_settings) as a float."""

    def value_fn(data: dict[str, Any]) -> float | None:
        raw = (data.get("settings") or {}).get(key)
        if raw in (None, ""):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    return value_fn


FEED_NUMBERS: tuple[DuneWeaverNumberDescription, ...] = (
    DuneWeaverNumberDescription(
        key="feed",
        translation_key="speed",
        native_min_value=1,
        native_max_value=100000,
        native_step=1,
        native_unit_of_measurement="mm/min",
        mode=NumberMode.BOX,
        value_fn=lambda d: d.get("feed"),
        set_fn=lambda coord, value: coord.async_set_feed(mm=int(value)),
    ),
    DuneWeaverNumberDescription(
        key="feed_override",
        translation_key="speed_override",
        native_min_value=10,
        native_max_value=200,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        value_fn=lambda d: d.get("feed_override"),
        set_fn=lambda coord, value: coord.async_set_feed(pct=int(value)),
    ),
)

# LED knobs — only added when the table has LEDs. Kept under the Configuration
# category since most only matter for specific effects (speed) or 'ball'.
LED_NUMBERS: tuple[DuneWeaverNumberDescription, ...] = (
    DuneWeaverNumberDescription(
        key="led_speed",
        translation_key="led_speed",
        entity_category=EntityCategory.CONFIG,
        native_min_value=1,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_led_setting("LED/Speed"),
        set_fn=lambda coord, value: coord.async_write_led(speed=int(value)),
    ),
    DuneWeaverNumberDescription(
        key="led_align",
        translation_key="led_align",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=359,
        native_step=1,
        native_unit_of_measurement="°",
        mode=NumberMode.SLIDER,
        value_fn=_led_setting("LED/Align"),
        set_fn=lambda coord, value: coord.async_write_led(align=int(value)),
    ),
    DuneWeaverNumberDescription(
        key="led_ball_size",
        translation_key="led_ball_size",
        entity_category=EntityCategory.CONFIG,
        native_min_value=1,
        native_max_value=200,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_led_setting("LED/BallSize"),
        set_fn=lambda coord, value: coord.async_write_led(size=int(value)),
    ),
    DuneWeaverNumberDescription(
        key="led_blob_brightness",
        translation_key="led_blob_brightness",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_led_setting("LED/BallBright"),
        set_fn=lambda coord, value: coord.async_write_led(fgbright=int(value)),
    ),
    DuneWeaverNumberDescription(
        key="led_bg_brightness",
        translation_key="led_bg_brightness",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_led_setting("LED/BallBgBright"),
        set_fn=lambda coord, value: coord.async_write_led(bgbright=int(value)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = list(FEED_NUMBERS)
    if "led" in coordinator.data:
        descriptions += LED_NUMBERS
    async_add_entities(
        DuneWeaverNumber(coordinator, description) for description in descriptions
    )


class DuneWeaverNumber(DuneWeaverEntity, NumberEntity):
    entity_description: DuneWeaverNumberDescription

    def __init__(
        self,
        coordinator: DuneWeaverCoordinator,
        description: DuneWeaverNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.coordinator, value)
