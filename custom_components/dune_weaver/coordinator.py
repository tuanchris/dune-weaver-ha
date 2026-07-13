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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.get_status()
        except DuneWeaverError as err:
            raise UpdateFailed(str(err)) from err
        if not self._settings_loaded:
            await self._refresh_settings()
        status["settings"] = self._settings
        return status

    async def _refresh_settings(self) -> None:
        """Reload /sand_settings — the source for LED palette/color/speed/ball
        state that /sand_status doesn't report."""
        try:
            self._settings = await self.client.get_settings()
            self._settings_loaded = True
        except DuneWeaverError as err:
            _LOGGER.debug("Could not load /sand_settings: %s", err)

    # -- mutations (refresh so entities reflect the new state) -----------------

    async def async_set_feed(
        self, *, mm: int | None = None, pct: int | None = None
    ) -> None:
        await self.client.set_feed(mm=mm, pct=pct)
        await self.async_request_refresh()

    async def async_write_led(self, **values: Any) -> None:
        """Apply live LED values (/sand_led), then reload settings + status so
        the color/palette/ball entities reflect the change."""
        await self.client.set_led(**values)
        await self._refresh_settings()
        await self.async_request_refresh()

    async def async_set_led_hook(self, hook: str, effect: str) -> None:
        """Set a machine-state effect override ($LED/RunEffect|IdleEffect)."""
        await self.client.command(f"$LED/{hook}={effect}")
        await self._refresh_settings()
        await self.async_request_refresh()
