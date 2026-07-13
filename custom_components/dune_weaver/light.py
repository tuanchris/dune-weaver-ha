"""LED strip of the table as a light entity.

Uses /sand_led — the firmware's live, non-idle-gated path — so LED changes work
mid-pattern; the firmware persists the values to NVS on the return to idle.

/sand_status only reports the live effect + brightness, so the current RGB color
is read back from /sand_settings (LED/Color), which the coordinator merges in.
Everything the light platform can't express (secondary color, palette, speed,
ball params) lives on the select/number entities and the dune_weaver.set_led
service registered here.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LED_DIRECTIONS, LED_EFFECTS
from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity

DEFAULT_BRIGHTNESS = 128

SERVICE_SET_LED = "set_led"
# Full LED surface for the service — a superset of what the light/select/number
# entities expose (adds color2 and every ball knob in one call).
_HEX = cv.matches_regex(r"^#?[0-9a-fA-F]{6}$")
SET_LED_SCHEMA = {
    vol.Optional("effect"): vol.In(LED_EFFECTS),
    vol.Optional("palette"): cv.string,
    vol.Optional("color"): _HEX,
    vol.Optional("color2"): _HEX,
    vol.Optional("brightness"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    vol.Optional("speed"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
    vol.Optional("direction"): vol.In(LED_DIRECTIONS),
    vol.Optional("align"): vol.All(vol.Coerce(int), vol.Range(min=0, max=359)),
    vol.Optional("size"): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
    vol.Optional("fgbright"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    vol.Optional("bgbright"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    vol.Optional("bg"): cv.string,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_LED, SET_LED_SCHEMA, "async_set_led_service"
    )
    # The firmware omits "led" entirely when no leds: config section exists.
    if "led" in coordinator.data:
        async_add_entities([DuneWeaverLight(coordinator)])


class DuneWeaverLight(DuneWeaverEntity, LightEntity):
    _attr_translation_key = "leds"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = [e for e in LED_EFFECTS if e != "off"]

    def __init__(self, coordinator: DuneWeaverCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_led"
        self._last_effect: str | None = None
        self._remember_effect()

    @property
    def _led(self) -> dict[str, Any]:
        return self.coordinator.data.get("led") or {}

    def _remember_effect(self) -> None:
        effect = self._led.get("effect")
        if effect and effect != "off":
            self._last_effect = effect

    @callback
    def _handle_coordinator_update(self) -> None:
        self._remember_effect()
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool:
        return self._led.get("effect") not in (None, "off")

    @property
    def brightness(self) -> int | None:
        return self._led.get("brightness")

    @property
    def effect(self) -> str | None:
        effect = self._led.get("effect")
        # "off" is not in effect_list (it maps to the light being off).
        return effect if effect and effect != "off" else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        # Primary color comes from /sand_settings (not /sand_status).
        raw = (self.coordinator.data.get("settings") or {}).get("LED/Color")
        if not raw:
            return None
        h = raw.lstrip("#")
        if len(h) != 6:
            return None
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        values: dict[str, Any] = {}
        if ATTR_BRIGHTNESS in kwargs:
            values["brightness"] = kwargs[ATTR_BRIGHTNESS]
        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            values["color"] = f"{r:02X}{g:02X}{b:02X}"
        if ATTR_EFFECT in kwargs:
            values["effect"] = kwargs[ATTR_EFFECT]
        if not self.is_on:
            # Coming from off: restore the last effect (or fall back to static),
            # and make sure brightness is non-zero so the strip actually lights.
            values.setdefault("effect", self._last_effect or "static")
            if "brightness" not in values and not self._led.get("brightness"):
                values["brightness"] = DEFAULT_BRIGHTNESS
        await self.coordinator.async_write_led(**values)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_led(effect="off")

    async def async_set_led_service(self, **values: Any) -> None:
        """dune_weaver.set_led — full LED control, including keys the light
        platform can't express (color2, palette, speed, ball params)."""
        cleaned = {k: v for k, v in values.items() if v is not None}
        for key in ("color", "color2"):
            if key in cleaned:
                cleaned[key] = str(cleaned[key]).lstrip("#").upper()
        await self.coordinator.async_write_led(**cleaned)
