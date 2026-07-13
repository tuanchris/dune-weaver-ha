"""Config flow for the Dune Weaver integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import DuneWeaverClient, DuneWeaverError
from .const import DOMAIN

USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class DuneWeaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle manual entry and zeroconf discovery of a table.

    The table's stable identity is its STA MAC: firmware exposes it both in
    /sand_status ("mac") and in the mDNS TXT record ("mac="), so a table added
    by IP and the same table found via discovery dedupe to one entry, and a
    DHCP address change just updates the host. Older firmware without the mac
    field falls back to the mDNS hostname (discovery) or no unique ID (manual).
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
                    await self.async_set_unique_id(format_mac(mac))
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                title = status.get("hostname") or host
                return self.async_create_entry(title=title, data={CONF_HOST: host})
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Discovery via the firmware's mDNS TXT record (model=dune-weaver)."""
        host = discovery_info.host
        hostname = (
            discovery_info.hostname.rstrip(".").removesuffix(".local").lower()
        )
        mac = discovery_info.properties.get("mac")
        await self.async_set_unique_id(format_mac(mac) if mac else hostname)
        # Table already configured (possibly by IP) → just track an IP change.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
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
