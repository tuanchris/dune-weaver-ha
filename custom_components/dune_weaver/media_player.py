"""Media player presenting table playback as a friendly card.

Maps the sand table onto the media_player model: transport controls
(play/pause/stop/next) drive the firmware's resume/pause/stop/skip; playlists
are exposed as sources; and the on-card pattern library is browsable as a folder
tree, with a selected pattern started via play_media.

No media position/duration is reported: the firmware gives fractional progress,
not time, and HA would extrapolate a time-based bar between the 2 s polls and
make it jitter. The Progress sensor carries the exact percentage instead.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DuneWeaverConfigEntry, DuneWeaverCoordinator
from .entity import DuneWeaverEntity

# Root id and the content type used for our pattern folders.
_ROOT = "root"
_FOLDER_TYPE = "pattern_folder"


def _strip_txt(name: str) -> str:
    return name[:-4] if name.lower().endswith(".txt") else name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuneWeaverConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([DuneWeaverMediaPlayer(entry.runtime_data)])


class DuneWeaverMediaPlayer(DuneWeaverEntity, MediaPlayerEntity):
    _attr_translation_key = "player"
    # NB: not assumed_state — that would render separate play/pause/stop buttons.
    # We keep the single state-dependent play/pause toggle; STOP is still
    # supported (more-info dialog / a dashboard button calling media_stop).
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
    )

    def __init__(self, coordinator: DuneWeaverCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_player"

    # -- state -----------------------------------------------------------------

    @property
    def state(self) -> MediaPlayerState:
        data = self.coordinator.data
        if data.get("state") == "Hold":
            return MediaPlayerState.PAUSED
        if data.get("running"):
            return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    @property
    def media_content_type(self) -> str | None:
        return MediaType.MUSIC if self.coordinator.data.get("running") else None

    @property
    def media_content_id(self) -> str | None:
        return self.coordinator.data.get("file") if self.coordinator.data.get("running") else None

    @property
    def media_title(self) -> str | None:
        data = self.coordinator.data
        if not data.get("running"):
            return None
        playlist = data.get("playlist") or {}
        if playlist.get("clearing"):
            return "Clearing…"
        file = data.get("file") or ""
        return file.rsplit("/", 1)[-1].removesuffix(".thr") or None

    @property
    def media_playlist(self) -> str | None:
        playlist = self.coordinator.data.get("playlist") or {}
        return playlist.get("name") if playlist.get("active") else None

    # -- sources = playlists ---------------------------------------------------

    @property
    def source_list(self) -> list[str]:
        return [_strip_txt(p) for p in (self.coordinator.data.get("playlists") or [])]

    @property
    def source(self) -> str | None:
        playlist = self.coordinator.data.get("playlist") or {}
        return _strip_txt(playlist.get("name") or "") or None if playlist.get("active") else None

    async def async_select_source(self, source: str) -> None:
        await self.coordinator.async_run_playlist(source)

    # -- transport -------------------------------------------------------------

    async def async_media_play(self) -> None:
        await self.coordinator.client.resume()
        await self.coordinator.async_request_refresh()

    async def async_media_pause(self) -> None:
        await self.coordinator.client.pause()
        await self.coordinator.async_request_refresh()

    async def async_media_stop(self) -> None:
        await self.coordinator.client.stop()
        await self.coordinator.async_request_refresh()

    async def async_media_next_track(self) -> None:
        await self.coordinator.client.playlist_skip()
        await self.coordinator.async_request_refresh()

    # -- browse + play patterns ------------------------------------------------

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        await self.coordinator.async_run_pattern(media_id)

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        patterns = self.coordinator.data.get("patterns") or []
        folder = "" if media_content_id in (None, _ROOT) else media_content_id
        return self._browse_folder(patterns, folder)

    def _browse_folder(self, patterns: list[str], folder: str) -> BrowseMedia:
        """Build one level of the pattern tree: immediate subfolders + files.
        `folder` is "" at the root, otherwise a "<path>/" prefix."""
        subfolders: dict[str, str] = {}
        files: list[str] = []
        for path in patterns:
            if not path.startswith(folder):
                continue
            rest = path[len(folder) :]
            if "/" in rest:
                sub = rest.split("/", 1)[0]
                subfolders.setdefault(sub, f"{folder}{sub}/")
            elif rest:
                files.append(path)

        children = [
            BrowseMedia(
                title=name,
                media_class=MediaClass.DIRECTORY,
                media_content_type=_FOLDER_TYPE,
                media_content_id=path,
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.MUSIC,
            )
            for name, path in sorted(subfolders.items())
        ]
        children += [
            BrowseMedia(
                title=path.rsplit("/", 1)[-1].removesuffix(".thr"),
                media_class=MediaClass.MUSIC,
                media_content_type=MediaType.MUSIC,
                media_content_id=path,
                can_play=True,
                can_expand=False,
            )
            for path in sorted(files)
        ]

        title = folder.rstrip("/").rsplit("/", 1)[-1] if folder else "Patterns"
        return BrowseMedia(
            title=title,
            media_class=MediaClass.DIRECTORY,
            media_content_type=_FOLDER_TYPE,
            media_content_id=folder or _ROOT,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.MUSIC,
        )
