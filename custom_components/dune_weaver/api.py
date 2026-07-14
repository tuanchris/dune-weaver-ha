"""Thin async client for the Dune Weaver sand-table HTTP API.

The firmware API is stateless, multi-client HTTP: *read* via the /sand_* JSON
routes, *act* via /command?plain=<cmd> (fire-and-forget) and the /sand_* action
routes. See API.md in the dune-weaver-firmware repo for the contract.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import ClientError, ClientSession

REQUEST_TIMEOUT = 10


class DuneWeaverError(Exception):
    """Base error talking to the table."""


class DuneWeaverConnectionError(DuneWeaverError):
    """The table could not be reached."""


class DuneWeaverResponseError(DuneWeaverError):
    """The table answered with an HTTP error (e.g. 409 IdleError)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class DuneWeaverBusyError(DuneWeaverResponseError):
    """The table shed this request under memory pressure (503 'busy: low
    memory'). Transient — back off and retry. /sand_status and the
    stop/pause/resume actions are exempt from the firmware's low-heap guard, so
    the heartbeat and safety controls keep working."""


class DuneWeaverClient:
    """Client for one table. Holds no connection state (plain HTTP)."""

    def __init__(self, host: str, session: ClientSession, port: int = 80) -> None:
        self.host = host
        self.base_url = f"http://{host}:{port}"
        self._session = session
        # The ESP32 web server handles ONE client at a time and is heap-tight.
        # Serialize every request so HA never has two connections (two lwIP
        # PCBs + socket buffers) alive against the board at once — e.g. a status
        # poll racing a slider drag's writes.
        self._lock = asyncio.Lock()

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}{path}"
        # Don't pool the connection: the board force-closes after every response
        # (Connection: close), so a pooled socket is already dead; closing our
        # side too avoids a doomed reuse attempt and keeps zero idle sockets.
        headers = {"Connection": "close"}
        try:
            async with self._lock, asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.get(url, params=params, headers=headers)
                body = await resp.text()
        except (TimeoutError, ClientError) as err:
            raise DuneWeaverConnectionError(f"Cannot reach {url}: {err}") from err
        if resp.status >= 400:
            detail = body.strip()[:200]
            if resp.status == 503 and "low memory" in detail.lower():
                raise DuneWeaverBusyError(resp.status, detail)
            raise DuneWeaverResponseError(resp.status, detail)
        return body

    async def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        body = await self._request(path, params)
        try:
            return json.loads(body)
        except ValueError as err:
            raise DuneWeaverError(f"Invalid JSON from {path}: {body[:100]!r}") from err

    # -- reads (multi-client JSON routes, safe during motion) -----------------

    async def get_status(self) -> dict[str, Any]:
        """GET /sand_status — the 1–2 Hz poll target."""
        status = await self._request_json("/sand_status")
        if not isinstance(status, dict) or "state" not in status:
            raise DuneWeaverError(f"Unexpected /sand_status payload: {status!r}")
        return status

    async def get_settings(self) -> dict[str, Any]:
        return await self._request_json("/sand_settings")

    async def get_patterns(self) -> list[str]:
        return await self._request_json("/sand_patterns")

    async def get_playlists(self) -> list[str]:
        return await self._request_json("/sand_playlists")

    # -- actions ---------------------------------------------------------------

    async def command(self, cmd: str) -> None:
        """Fire-and-forget command via /command?plain= (confirm via status poll)."""
        await self._request("/command", {"plain": cmd})

    async def home(self) -> None:
        """Home honoring $Sand/HomingMode; runs in the firmware main loop."""
        await self._request("/sand_home")

    async def stop(self) -> None:
        await self._request("/sand_stop")

    async def pause(self) -> None:
        await self._request("/sand_pause")

    async def resume(self) -> None:
        await self._request("/sand_resume")

    async def set_feed(self, mm: int | None = None, pct: int | None = None) -> None:
        """Set base feed (mm/min) and/or override % — both work mid-pattern."""
        params: dict[str, Any] = {}
        if mm is not None:
            params["mm"] = int(mm)
        if pct is not None:
            params["pct"] = int(pct)
        if params:
            await self._request("/sand_feed", params)

    async def set_led(self, **values: Any) -> None:
        """Live LED control (/sand_led) — not idle-gated, persisted on idle."""
        if values:
            await self._request("/sand_led", values)

    async def run_pattern(self, path: str, clear: str | None = None) -> None:
        """Run a .thr pattern. `path` is a /sand_patterns entry (relative to
        /patterns) or an absolute SD path. With a clear mode, $Sand/Run
        sequences a clear move first; otherwise $SD/Run (which works even on
        configs without a playlist: section)."""
        full = path if path.startswith("/") else f"/patterns/{path}"
        if clear and clear != "none":
            await self.command(f"$Sand/Run={full} clear={clear}")
        else:
            await self.command(f"$SD/Run={full}")

    async def run_playlist(self, name: str) -> None:
        """Run playlist /playlists/<name>.txt (the .txt suffix is optional)."""
        if name.lower().endswith(".txt"):
            name = name[:-4]
        await self.command(f"$Playlist/Run={name}")

    async def playlist_stop(self) -> None:
        """Stop after the current pattern finishes."""
        await self.command("$Playlist/Stop")

    async def playlist_skip(self) -> None:
        """Abort the current pattern and advance to the next."""
        await self.command("$Playlist/Skip")
