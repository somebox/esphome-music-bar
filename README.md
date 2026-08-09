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

**Status: spec only.** The design is written down in
[`docs/spec.md`](docs/spec.md); no configuration has been ported into this repo
yet. It descends from a working private build, so the hard parts are known
rather than guessed — see "Prior art" below.

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

## Prior art

This is an extraction of `hifi-panel`, a working single-file config built in
August 2026 for a WiiM speaker. That build proved out album art decoding, LVGL
rotation, touch hit-testing, build-time logo fetching and the Music Assistant
image proxy's real behaviour. `docs/spec.md` carries those findings forward as
constraints, and the parts of it marked *proven* were measured on hardware.

## License

Not yet chosen.
