# ma-bar-3.49

An ESPHome media panel for **Music Assistant**, running on the **Waveshare
ESP32-S3-Touch-LCD-3.49** — a 640×172 touch "bar" that sits next to a speaker
and shows what's playing, with tappable transport controls and a browser for
your Music Assistant favorites.

The name encodes the two things this project is actually tied to. It is not a
general ESPHome dashboard: it assumes that exact board (its display driver,
resolution, pin map and sensors) and it assumes Music Assistant as the backend
(its image proxy, library API and playback service). Any speaker Music
Assistant can drive will work — the panel never talks to the player directly.

Your favorites, and what the browser shows, are read at runtime. Changing them
never means rebuilding or reflashing the panel.

**Status: spec only.** The design is written down in
[`docs/spec.md`](docs/spec.md); no configuration has been ported into this repo
yet. It descends from a working private build, so the hard parts are known
rather than guessed — see "Prior art" below.

## How it fits together

Three pieces:

- **The ESPHome config** on the panel. Fixed widgets, no content — it renders
  whatever it is handed.
- **A Home Assistant package** that resolves item names against Music
  Assistant, and pushes a page of five items to the panel when it asks.
- **An artwork normalizer** that returns every image at identical dimensions,
  filling gaps from your own override folder. Not cosmetic: ESPHome
  reallocates an image buffer whenever the decoded dimensions change, and
  varying artwork sizes fragment PSRAM until the panel falls over.
  [`docs/spec.md` §4](docs/spec.md#4-artwork) has the details.

## Hardware

- **Board**: Waveshare ESP32-S3-Touch-LCD-3.49. AXS15231B QSPI display and
  capacitive touch (one chip drives both), 172×640 native portrait, used
  rotated 90° as a 640×172 landscape bar.
- **Also on board**: QMI8658 IMU on a second I²C bus (GPIO47/48), for
  auto-rotating the display when the panel is mounted the other way up.
- **Power**: mains. There is a battery circuit; this project does not use it.

## Requirements

- Music Assistant 2.x, reachable over plain HTTP on the LAN
- Home Assistant with the Music Assistant integration
- ESPHome 2026.5 or newer (earlier versions rotate LVGL touch input incorrectly)

## Artwork, and why some tiles show initials

**This repo ships no artwork.** Station logos and album covers belong to the
people who made them, so none are included and none are ever committed —
everything under `overrides/` is gitignored, so a fork cannot publish them by
accident. What you see on your panel is fetched by you, from your own Music
Assistant, onto your own machine.

Music Assistant does not have artwork for everything. For anything it lacks,
the panel shows a monogram: the item's initials on a colour derived from its
name. Deterministic, so an item keeps its colour, and distinct, so a page of
them looks like a design rather than a row of identical failure icons.

### Replacing one

After the first normalizer run, open **`http://<your-ha>:8123/local/ma-bar/`**.
It lists every tile the panel can show, initials-only ones first, each with the
exact filename it wants.

1. Save your image with that filename. Any size, any shape, transparent or not
   — `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` all work.
2. Put it in the `overrides/` folder (or wherever `artwork.overrides_dir`
   points).
3. Run the normalizer again, or press **Refresh artwork** on your dashboard.

The panel updates on its next page turn. No reflash, no restart. You never need
to know a slug, an ID, or an image size — the page tells you the filename and
the normalizer handles the rest.

Prefer a terminal? `scripts/normalize-artwork.py --report` prints the same
thing and writes nothing.

### What happens when things change

| You do this | What happens |
|---|---|
| **Update the firmware** | Nothing to redo. The panel stores no content — names, URIs and artwork URLs all arrive from Home Assistant at boot. Your overrides are on disk and untouched. |
| **Change `tile_px` and reflash** | Every cached image is now the wrong size, which breaks the fixed-dimension rule the panel depends on. Rerun the normalizer. It records `tile_px` in the manifest and the Home Assistant package refuses to push mismatched artwork rather than letting the panel destabilise. |
| **Favorite something new** | It appears on the next page turn — pages are built live from Music Assistant. Its artwork is generated on the next normalizer run, which Home Assistant triggers as soon as it sees an item it has no image for. |
| **Unfavorite something** | It drops off the next page turn. Its image file is left behind harmlessly. |
| **A station gains a logo it never had** | Picked up on the next normalizer run, which re-checks Music Assistant for anything still on a monogram rather than caching the absence. New artwork means a new fingerprint, a new URL, and the panel refetches on its next page turn. |
| **You add an override for something that already had artwork** | Yours wins. The order is your file, then Music Assistant, then a monogram, and it is checked fresh every run. |
| **You rename an item in Music Assistant** | The new name makes a new slug, so the old override filename stops matching and the tile falls back to a monogram. The normalizer lists override files that match nothing, and the gallery shows the filename now wanted — rename the file. |

## Prior art

This is an extraction of `hifi-panel`, a working single-file config built in
August 2026 for a WiiM speaker. That build proved out album art decoding, LVGL
rotation, touch hit-testing, build-time logo fetching and the Music Assistant
image proxy's real behaviour. `docs/spec.md` carries those findings forward as
constraints, and the parts of it marked *proven* were measured on hardware.

## License

MIT — see [LICENSE](LICENSE).
