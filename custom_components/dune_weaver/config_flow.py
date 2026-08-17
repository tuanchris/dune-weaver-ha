"""Config flow for the Dune Weaver integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import DuneWeaverClient, DuneWeaverError
from .const import DOMAIN

USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class DuneWeaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle manual entry and discovery of a table.

    The table's stable identity is its STA MAC: firmware exposes it both in
    /sand_status ("mac") and in the mDNS TXT record ("mac="), so a table added
    by IP and the same table found via discovery dedupe to one entry. Older
    firmware without the mac field falls back to the mDNS hostname (discovery)
    or no unique ID (manual); __init__ claims the MAC as the unique ID as soon
    as the table reports one, so those entries catch up on their next reload.

    Tables move: DHCP hands out a new lease, the user swaps a router, the table
    is re-flashed. Three paths follow that address change, in the order they
    normally win — mDNS (the firmware re-announces its new address and HA
    re-fires this flow), DHCP (the lease itself, for networks where mDNS is
    filtered), and finally the reconfigure step for a hand-typed fix. All three
    update CONF_HOST on the *existing* entry, so entity IDs and automations
    survive the move.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str = "Dune Weaver"

    async def _async_validate(self, host: str) -> dict[str, Any]:
        """Fetch /sand_status to prove the host is a reachable sand table."""
        client = DuneWeaverClient(host, async_get_clientsession(self.hass))
        return await client.get_status()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual host entry (the fallback when mDNS is flaky)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            self._async_abort_entries_match({CONF_HOST: host})
            try:
                status = await self._async_validate(host)
            except DuneWeaverError:
                errors["base"] = "cannot_connect"
            else:
                if mac := status.get("mac"):
                    entry = await self.async_set_unique_id(format_mac(mac))
                    # Re-adding a known table at a new address is how a user
                    # who never found the reconfigure button fixes a moved
                    # table — treat it as an address update, not a duplicate.
                    if entry is not None and entry.data.get(CONF_HOST) != host:
                        return self.async_update_reload_and_abort(
                            entry,
                            data_updates={CONF_HOST: host},
                            reason="address_updated",
                        )
                    self._abort_if_unique_id_configured()
                title = status.get("hostname") or host
                return self.async_create_entry(title=title, data={CONF_HOST: host})
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point an existing entry at a new address, keeping its entities.

        The manual escape hatch for a table that moved somewhere neither mDNS
        nor DHCP could tell us about (a different subnet, a static IP change).
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                status = await self._async_validate(host)
            except DuneWeaverError:
                errors["base"] = "cannot_connect"
            else:
                unique_id = entry.unique_id
                if mac := status.get("mac"):
                    found = format_mac(mac)
                    other = self.hass.config_entries.async_entry_for_domain_unique_id(
                        DOMAIN, found
                    )
                    if unique_id is not None and unique_id != found:
                        # Repointing an entry at a *different* table would hand
                        # that table this one's entity IDs and history.
                        return self.async_abort(reason="wrong_table")
                    if other is not None and other.entry_id != entry.entry_id:
                        return self.async_abort(reason="already_configured")
                    # Entry predates the firmware reporting a MAC: claim it now.
                    unique_id = found
                return self.async_update_reload_and_abort(
                    entry, unique_id=unique_id, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_HOST: entry.data[CONF_HOST]}
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Discovery via the firmware's mDNS TXT record (model=dune-weaver).

        HA re-fires this when a known service's address changes, so this is the
        usual path by which a DHCP move gets followed.
        """
        host = discovery_info.host
        hostname = (
            discovery_info.hostname.rstrip(".").removesuffix(".local").lower()
        )
        mac = discovery_info.properties.get("mac")
        await self.async_set_unique_id(format_mac(mac) if mac else hostname)
        # Table already configured (possibly by IP) → just track an IP change.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        if not mac:
            # Without a MAC we can't tell "same table, new address" from "new
            # table on an address a moved table used to hold", so dedupe on the
            # address itself. With a MAC, skip it: a stale entry still pointing
            # at this IP must not block discovering whoever holds it now.
            self._async_abort_entries_match({CONF_HOST: host})
        try:
            await self._async_validate(host)
        except DuneWeaverError:
            return self.async_abort(reason="cannot_connect")
        self._host = host
        self._name = hostname.upper() or "Dune Weaver"
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm adding the discovered table."""
        if user_input is not None:
            assert self._host is not None
            return self.async_create_entry(
                title=self._name, data={CONF_HOST: self._host}
            )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._name, "host": self._host or ""},
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow a lease change for a table we already track.

        The manifest declares only a `registered_devices` matcher, so this runs
        solely for MACs this integration already has in the device registry —
        it exists to move CONF_HOST, never to add a table (a DHCP packet says
        nothing about whether the device speaks the sand-table API). It covers
        the networks where mDNS never reaches HA.
        """
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        return self.async_abort(reason="unknown_device")
