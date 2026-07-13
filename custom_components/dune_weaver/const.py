"""Constants for the Dune Weaver integration."""

from __future__ import annotations

DOMAIN = "dune_weaver"

DEFAULT_PORT = 80
UPDATE_INTERVAL_SECONDS = 2

# Effect names accepted by the firmware ($LED/Effect / /sand_led?effect=).
LED_EFFECTS = [
    "off",
    "static",
    "rainbow",
    "breathe",
    "colorloop",
    "theater",
    "scan",
    "running",
    "sine",
    "gradient",
    "sinelon",
    "twinkle",
    "sparkle",
    "fire",
    "candle",
    "meteor",
    "bouncing",
    "wipe",
    "dualscan",
    "juggle",
    "multicomet",
    "glitter",
    "dissolve",
    "ripple",
    "drip",
    "lightning",
    "fireworks",
    "plasma",
    "heartbeat",
    "strobe",
    "police",
    "chase",
    "railway",
    "pacifica",
    "aurora",
    "pride",
    "colorwaves",
    "bpm",
    "ball",
]

# Palettes that recolor the hue-cycling effects ($LED/Palette / /sand_led?palette=).
LED_PALETTES = [
    "rainbow",
    "ocean",
    "lava",
    "forest",
    "party",
    "cloud",
    "heat",
    "sunset",
]

# 'ball' effect ring winding direction ($LED/Direction / /sand_led?direction=).
LED_DIRECTIONS = ["cw", "ccw"]

# What the 'ball' effect renders behind the blob (/sand_led?bg=): a solid color
# ("static"), black ("off"), or any non-ball animated effect.
LED_BALL_BG_OPTIONS = ["static", "off"] + [
    e for e in LED_EFFECTS if e not in ("ball", "off", "static")
]

# Machine-state effect override for $LED/RunEffect and $LED/IdleEffect:
# "none" leaves the manual effect in place, otherwise any effect name.
LED_HOOK_OPTIONS = ["none"] + LED_EFFECTS
