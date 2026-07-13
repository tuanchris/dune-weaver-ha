"""Sensors derived from the /sand_status poll."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity


@dataclass(frozen=True, kw_only=True)
class DuneWeaverSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], StateType]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _progress(data: dict[str, Any]) -> float | None:
    # -1 = unknown (e.g. during a pre-execution clear's setup) → unknown state.
    progress = data.get("progress", -1)
    return round(progress * 100, 1) if progress >= 0 else None


def _pattern(data: dict[str, Any]) -> str | None:
    if not data.get("running"):
        return None
    file = data.get("file") or ""
    return file.rsplit("/", 1)[-1].removesuffix(".thr") or None


def _playlist(data: dict[str, Any]) -> str | None:
    playlist = data.get("playlist") or {}
    return playlist.get("name") if playlist.get("active") else None


def _playlist_attrs(data: dict[str, Any]) -> dict[str, Any]:
    playlist = data.get("playlist") or {}
    if not playlist.get("active"):
        return {}
    return {
        "index": playlist.get("index"),
        "total": playlist.get("total"),
        "clearing": playlist.get("clearing"),
        "quiet_hours": playlist.get("quiet"),
        "pause_remaining": playlist.get("pause_remaining"),
        "pause_total": playlist.get("pause_total"),
    }


SENSORS: tuple[DuneWeaverSensorDescription, ...] = (
    DuneWeaverSensorDescription(
        key="state",
        translation_key="table_state",
        value_fn=lambda d: d.get("state"),
    ),
    DuneWeaverSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=_progress,
    ),
    DuneWeaverSensorDescription(
        key="pattern",
        translation_key="current_pattern",
        value_fn=_pattern,
    ),
    DuneWeaverSensorDescription(
        key="playlist",
        translation_key="playlist",
        value_fn=_playlist,
        attrs_fn=_playlist_attrs,
    ),
    DuneWeaverSensorDescription(
        key="last_reset",
        translation_key="last_reset_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("last_reset"),
    ),
    DuneWeaverSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("uptime"),
    ),
    DuneWeaverSensorDescription(
        key="heap",
        translation_key="free_heap",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("heap"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DuneWeaverSensor(coordinator, description) for description in SENSORS
    )


class DuneWeaverSensor(DuneWeaverEntity, SensorEntity):
    entity_description: DuneWeaverSensorDescription

    def __init__(
        self,
        coordinator: DuneWeaverCoordinator,
        description: DuneWeaverSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
