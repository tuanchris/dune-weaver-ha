# Brand assets

Home Assistant and HACS **do not** read an integration's icon from this
repository — they load it from the central
[`home-assistant/brands`](https://github.com/home-assistant/brands) repo. Until
this domain is added there, HACS shows an "icon not available" placeholder.

The files in `dune_weaver/` are prepared to the brands spec (square, transparent,
256×256 `icon.png` + 512×512 `icon@2x.png`, plus matching `logo.png`) so they can
be submitted as-is.

## To make the icon appear in HACS / HA

Open a PR against `home-assistant/brands` placing these files at:

```
custom_integrations/dune_weaver/icon.png       (256×256)
custom_integrations/dune_weaver/icon@2x.png     (512×512)
custom_integrations/dune_weaver/logo.png
custom_integrations/dune_weaver/logo@2x.png
```

Once that PR merges, `brands.home-assistant.io` serves the icon and it shows up
automatically in HACS and on the integration/device pages (no integration
release needed).

Source artwork: `logo_alt.png` from the Dune Weaver website (the shaded mark,
chosen over the line-art version so it stays legible on HA's dark theme).
