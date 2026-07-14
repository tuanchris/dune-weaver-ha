"""Polling coordinator for the Dune Weaver integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DuneWeaverClient, DuneWeaverError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

type DuneWeaverConfigEntry = ConfigEntry[DuneWeaverCoordinator]

# /sand_led live keys -> the /sand_settings key they persist to. Used to fold a
# write into the cached settings optimistically, so an LED change doesn't cost a
# GET /sand_settings on top of the write (the ESP32 serves HTTP serially).
_LED_LIVE_TO_SETTING = {
    "effect": "LED/Effect",
    "palette": "LED/Palette",
    "color": "LED/Color",
    "color2": "LED/Color2",
    "brightness": "LED/Brightness",
    "speed": "LED/Speed",
    "direction": "LED/Direction",
    "align": "LED/Align",
    "size": "LED/BallSize",
    "fgbright": "LED/BallBright",
    "bgbright": "LED/BallBgBright",
    "bg": "LED/BallBg",
}


class DuneWeaverCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls GET /sand_status — the poll rate the firmware was designed for."""

    config_entry: DuneWeaverConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: DuneWeaverConfigEntry,
        client: DuneWeaverClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        # /sand_status only reports led effect+brightness; the rest of the LED
        # state (palette, color, color2, speed, ball params, run/idle hooks) and
        # the persisted feed live in /sand_settings. Settings change rarely, so
        # we cache them and reload only on first poll and after a write.
        self._settings: dict[str, str] = {}
        self._settings_loaded = False
        # Pattern + playlist catalogs (/sand_patterns, /sand_playlists). Fetched
        # once and cached — the lists can be large and change rarely, so they're
        # reloaded only via the "Refresh library" button, not on the poll loop.
        self._patterns: list[str] = []
        self._playlists: list[str] = []
        self._library_loaded = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.get_status()
        except DuneWeaverError as err:
            raise UpdateFailed(str(err)) from err
        if not self._settings_loaded:
            await self._refresh_settings()
        if not self._library_loaded:
            self._library_loaded = await self._refresh_library()
        status["settings"] = self._settings
        status["patterns"] = self._patterns
        status["playlists"] = self._playlists
        return status

    async def _refresh_settings(self) -> None:
        """Reload /sand_settings — the source for LED palette/color/speed/ball
        state that /sand_status doesn't report."""
        try:
            self._settings = await self.client.get_settings()
            self._settings_loaded = True
        except DuneWeaverError as err:
            _LOGGER.debug("Could not load /sand_settings: %s", err)

    async def _refresh_library(self) -> bool:
        """Load the pattern + playlist catalogs. Returns True if both succeeded."""
        ok = True
        try:
            self._patterns = await self.client.get_patterns()
        except DuneWeaverError as err:
            _LOGGER.debug("Could not load /sand_patterns: %s", err)
            ok = False
        try:
            self._playlists = await self.client.get_playlists()
        except DuneWeaverError as err:
            _LOGGER.debug("Could not load /sand_playlists: %s", err)
            ok = False
        return ok

    # -- mutations (refresh so entities reflect the new state) -----------------

    async def async_set_feed(
        self, *, mm: int | None = None, pct: int | None = None
    ) -> None:
        await self.client.set_feed(mm=mm, pct=pct)
        await self.async_request_refresh()

    async def async_write_led(self, **values: Any) -> None:
        """Apply live LED values (/sand_led) and fold them into the cached
        settings optimistically — /sand_status only echoes effect+brightness, so
        the cache is the source for color/palette/ball state. Entities clamp to
        the firmware's ranges before this, so the cache matches what's stored;
        this avoids a GET /sand_settings on every change (important during a
        color-wheel or slider drag)."""
        await self.client.set_led(**values)
        for key, val in values.items():
            if (setting := _LED_LIVE_TO_SETTING.get(key)) is not None:
                self._settings[setting] = (
                    str(val).upper() if key in ("color", "color2") else str(val)
                )
        await self.async_request_refresh()

    async def async_set_led_hook(self, hook: str, effect: str) -> None:
        """Set a machine-state effect override ($LED/RunEffect|IdleEffect)."""
        await self.client.command(f"$LED/{hook}={effect}")
        self._settings[f"LED/{hook}"] = effect
        await self.async_request_refresh()

    async def async_refresh_library(self) -> None:
        """Re-sync the cached catalogs and settings from the table (Refresh
        button). Also picks up LED/feed settings changed elsewhere (mobile app,
        table UI) that optimistic writes alone wouldn't surface."""
        await self._refresh_settings()
        await self._refresh_library()
        self._library_loaded = True
        await self.async_request_refresh()

    async def async_run_pattern(self, path: str, clear: str | None = None) -> None:
        await self.client.run_pattern(path, clear)
        await self.async_request_refresh()

    async def async_run_playlist(self, name: str) -> None:
        await self.client.run_playlist(name)
        await self.async_request_refresh()

    async def async_stop_playlist(self) -> None:
        await self.client.playlist_stop()
        await self.async_request_refresh()
