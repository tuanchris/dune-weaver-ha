"""The Dune Weaver integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .api import DuneWeaverClient
from .const import DOMAIN
from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: DuneWeaverConfigEntry) -> bool:
    """Set up a table from a config entry."""
    client = DuneWeaverClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    coordinator = DuneWeaverCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    _async_adopt_mac_unique_id(hass, entry, coordinator.data.get("mac"))
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DuneWeaverConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_adopt_mac_unique_id(
    hass: HomeAssistant, entry: DuneWeaverConfigEntry, mac: str | None
) -> None:
    """Claim the table's MAC as the entry's unique ID once it reports one.

    Entries added before the firmware exposed a MAC are keyed by mDNS hostname
    or by nothing at all, which is exactly the state in which an address change
    strands them: mDNS and DHCP discovery both match on the MAC, so neither can
    recognise the entry as the table that just moved. Adopting the MAC here
    makes those older entries self-healing from their next reload onward.

    Entity unique IDs are derived from the entry ID, not from this, so the
    change is invisible to the entity registry.
    """
    if not mac:
        return
    unique_id = format_mac(mac)
    if entry.unique_id == unique_id:
        return
    other = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
    if other is not None and other.entry_id != entry.entry_id:
        # Two entries for one table (e.g. added twice before the MAC existed).
        # Leave the duplicate alone rather than fight over the ID.
        _LOGGER.warning(
            "Not claiming MAC %s for %s: already used by %s",
            unique_id,
            entry.title,
            other.title,
        )
        return
    hass.config_entries.async_update_entry(entry, unique_id=unique_id)
