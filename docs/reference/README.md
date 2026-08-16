# Reference material

## hifi-panel

The working single-file build this project was extracted from: one Waveshare
ESP32-S3-Touch-LCD-3.49 next to a WiiM streamer, built August 2026.

**It is not in this repository, and should not be added to it.** The file
carries a baked `api.encryption.key` and an OTA password for a live device, and
this repo is public. It lives in the ESPHome dashboard on the Home Assistant
host, which is the copy to consult.

Its comments record findings that were expensive to learn, so they were carried
across rather than left behind:

| From hifi-panel | Now lives in |
|---|---|
| QSPI pins, display, touch, backlight, I2C buses | `esphome/devices/waveshare-3.49.yaml` |
| QMI8658 orientation logic, thresholds and debounce | same file, `check_orientation` |
| Fonts, verified MDI codepoints, LVGL theme, Now Playing layout | `esphome/music-bar.base.yaml` |
| The artwork traps — byte order, alpha, re-binding on download | comments on the `image:` block in the base |
| Album-art decode cost, proxy behaviour, the two-port quirk | `docs/spec.md` §4 and §6 |

Two things were deliberately **not** carried across:

- **Build-time station logos.** hifi-panel compiled each station logo into flash
  as `image: platform: file` at 84×84, which is why its browser tiles showed
  artwork. It also meant changing your favorites required regenerating the
  config and reflashing — the single thing this rewrite exists to remove. Tile
  artwork returns as runtime images fed by the normalizer; see `docs/plan.md`
  phase 4.
- **A second JPEG image slot.** hifi-panel carried one because Spotify Connect
  has no Music Assistant proxy path, so its artwork is a CDN JPEG and `format:`
  is fixed at compile time. This project has only the PNG slot; artwork for a
  Spotify Connect stream will not decode until that is added back.
