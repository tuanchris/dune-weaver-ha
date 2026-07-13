"""Base entity for the Dune Weaver integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DuneWeaverCoordinator


class DuneWeaverEntity(CoordinatorEntity[DuneWeaverCoordinator]):
    """One entity of a table; all entities share the table's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DuneWeaverCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dune Weaver",
            model="Sand table",
            sw_version=coordinator.data.get("fw"),
            configuration_url=coordinator.client.base_url,
        )
        if mac := coordinator.data.get("mac"):
            info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(mac))}
        self._attr_device_info = info
