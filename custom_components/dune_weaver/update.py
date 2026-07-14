"""Firmware update entity — notification only.

Installed version comes from /sand_status (`fw`) via the coordinator; the latest
release is checked against the firmware repo's GitHub releases on a slow, self-
paced timer (NOT the 5 s status poll — GitHub is rate-limited and this changes
rarely). Version handling mirrors the mobile app: only a strictly newer release
nags, and prereleases (`-preN`) sort below the matching release.

No install feature: flashing the ESP32 over HTTP is a brick risk, so this only
surfaces that an update exists and links to the release. Update via the mobile
app or the table's web UI.
"""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta

from aiohttp import ClientError
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity

_FIRMWARE_REPO = "tuanchris/dune-weaver-firmware"
_LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{_FIRMWARE_REPO}/releases/latest"
)
_RELEASES_URL = f"https://github.com/{_FIRMWARE_REPO}/releases"
_CHECK_INTERVAL = timedelta(hours=6)
_FETCH_TIMEOUT = 15

# git-describe-shaped: "v0.1.2", "v0.1.2-pre1", "v0.1.2 (main-abc1234-dirty)".
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-pre(\d+))?")


def _parse_version(value: str | None) -> tuple[int, int, int, float] | None:
    """Sort key [major, minor, patch, pre]; a full release outranks its -preN."""
    if not value:
        return None
    match = _VERSION_RE.search(value)
    if not match:
        return None
    pre = int(match.group(4)) if match.group(4) is not None else float("inf")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), pre)


def _canonical(value: str | None) -> str | None:
    """Normalize to 'vMAJOR.MINOR.PATCH[-preN]' (drops the git hash suffix)."""
    if not value:
        return None
    match = _VERSION_RE.search(value)
    if not match:
        return None
    base = f"v{match.group(1)}.{match.group(2)}.{match.group(3)}"
    return f"{base}-pre{match.group(4)}" if match.group(4) is not None else base


def _is_newer(candidate: str | None, current: str | None) -> bool:
    """True only when candidate is strictly newer (never nag on unknowns)."""
    a = _parse_version(candidate)
    b = _parse_version(current)
    return bool(a and b and a > b)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([DuneWeaverUpdate(entry.runtime_data)])


class DuneWeaverUpdate(DuneWeaverEntity, UpdateEntity):
    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, coordinator: DuneWeaverCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_firmware"
        self._latest_tag: str | None = None
        self._release_notes: str | None = None
        self._attr_release_url = _RELEASES_URL

    @property
    def installed_version(self) -> str | None:
        return _canonical(self.coordinator.data.get("fw"))

    @property
    def latest_version(self) -> str | None:
        installed = self.installed_version
        if self._latest_tag and _is_newer(self._latest_tag, installed):
            return self._latest_tag
        # No newer release known -> report installed so HA shows "up to date"
        # (and never nags when the table runs a build ahead of the latest tag).
        return installed

    async def async_release_notes(self) -> str | None:
        return self._release_notes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_check_latest()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._handle_interval, _CHECK_INTERVAL
            )
        )

    @callback
    def _handle_interval(self, _now) -> None:
        self.hass.async_create_task(self._async_check_latest())

    async def _async_check_latest(self) -> None:
        """Best-effort GitHub release check; keep the last answer on failure."""
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(_FETCH_TIMEOUT):
                resp = await session.get(
                    _LATEST_RELEASE_URL,
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status != 200:
                    return
                data = await resp.json()
        except (TimeoutError, ClientError, ValueError):
            return
        if not isinstance(data, dict) or not (tag := data.get("tag_name")):
            return
        self._latest_tag = tag
        self._attr_release_url = data.get("html_url") or _RELEASES_URL
        self._release_notes = data.get("body") or None
        self.async_write_ha_state()
