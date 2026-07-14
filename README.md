<img src="custom_components/dune_weaver/brand/icon@2x.png" alt="Dune Weaver" width="110" align="right">

# Dune Weaver — Home Assistant integration

Local-polling Home Assistant integration for [Dune Weaver](https://github.com/tuanchris/dune-weaver)
kinetic sand tables running the **standalone ESP32 firmware**
(FluidNC fork, `dune-weaver-firmware`). Talks directly to the table's HTTP API —
no MQTT broker, no Raspberry Pi.

## Features

- **Auto-discovery** — tables advertise `model=dune-weaver` over mDNS and show up
  in Home Assistant automatically (manual IP entry as fallback).
- **Light** — the table's LED ring as a proper HA light: on/off, brightness,
  RGB color (read back from the table), and all firmware effects. Uses the
  firmware's live LED path, so it works while a pattern is drawing.
- **Full LED control** — the light covers the basics; the rest of the firmware's
  LED surface is exposed as its own entities (under the device's *Configuration*
  section): **palette**, animation **speed**, the machine-state **run/idle effect**
  hooks, and every `ball`-effect parameter (**direction, alignment, glow size,
  blob & background brightness, background sub-effect**). The one thing HA's light
  platform can't model — a **secondary color** — plus any of the above in a single
  call is available through the `dune_weaver.set_led` service.
- **Sensors** — table state, pattern progress (%), current pattern, active
  playlist (with index/total/pause attributes), plus diagnostics
  (last restart reason, uptime, free memory).
- **Playback** — `select` entities to **start a pattern or playlist** from the
  table's on-card library. The lists are fetched once and cached (they can be
  large); a **Refresh library** button re-reads them on demand.
- **Media player** — a playback card: play/pause/stop/next, the current pattern
  as the title, playlists as selectable sources, and the pattern library as a
  browsable folder tree (pick one to run it).
- **Buttons** — Home, Stop, Pause, Resume, Skip pattern, Stop playlist, and
  Refresh library.
- **Numbers** — base speed (mm/min) and live speed override (%), both applied
  mid-pattern.
- **Update** — an `update` entity that surfaces the firmware version (`fw`) and
  notifies when a newer release is available (checked against the firmware
  repo's GitHub releases every 6 h). Notification only, with release notes and a
  link — flash from the mobile app or the table's web UI.

State is polled from `GET /sand_status` every 5 s — a background cadence that
keeps the integration's footprint small on the table's single-client,
heap-constrained web server (the mobile app is the realtime driver). All
requests are serialized, so the integration never holds more than one connection
to the board at a time. When `/sand_status` reports heap pressure
(`heap_largest` under 20 KB — e.g. while the app's launch burst and its
`/sand_patterns` read are running), the poll backs off to 30 s and the
integration defers its own catalog/settings reads, so it stops competing for the
last few KB of heap and can't push the board into its low-memory load-shedding.
The slower-changing LED/feed settings (`GET /sand_settings`, the source for the
palette/color/speed/ball values that `/sand_status` doesn't report) and the
pattern/playlist catalogs are fetched once when heap is healthy and re-read after
each write or via the refresh button, not on every poll.

## Requirements

- A table running `dune-weaver-firmware` (the standalone MKS-DLC32/ESP32 build).
  The Raspberry Pi-based Dune Weaver host is **not** supported by this
  integration (it has its own MQTT support).
- Home Assistant 2025.1 or newer.
- Firmware newer than v0.1.7 exposes the table's MAC address (in `/sand_status`
  and the mDNS TXT record); the integration uses it as the stable device ID, so
  a table added by IP and the same table found via discovery can't create
  duplicates, and DHCP address changes are followed automatically. Older
  firmware still works, just without that dedupe.

## Installation

### HACS (recommended)

1. HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/tuanchris/dune-weaver-ha` as an **Integration**.
3. Install **Dune Weaver**, restart Home Assistant.

### Manual

Copy `custom_components/dune_weaver/` into your HA `config/custom_components/`
directory and restart.

## Setup

Discovered tables appear under **Settings → Devices & services** — just confirm.
To add one manually: **Add integration → Dune Weaver** and enter the table's IP
address (prefer the IP over `<host>.local` if mDNS is unreliable on your
network).

Automations can also start playback with the `dune_weaver.run_pattern`
(path + optional `clear` mode) and `dune_weaver.run_playlist` services — handy
for passing a path that isn't in the cached list.
