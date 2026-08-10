# Reference material

`hifi-panel.yaml` is the working single-file build this project was extracted
from: one Waveshare ESP32-S3-Touch-LCD-3.49 next to a WiiM streamer, built
August 2026. It is kept here unmodified because its comments record findings
that were expensive to learn and are not written down anywhere else — the
AXS15231B pin map and init, why LVGL rotation and touch transforms interact the
way they do, what Music Assistant's image proxy actually returns, and several
ways an image decodes cleanly and still renders wrong.

It is **not built**. Nothing in the repo includes it, and it will not validate
as-is: it carries a baked API key, an OTA password and `!secret` references
this project deliberately does not use.

What was carried across, and where it went:

| From hifi-panel | Now lives in |
|---|---|
| SPI/QSPI pins, display, touch, backlight, I2C buses | `esphome/devices/waveshare-3.49.yaml` |
| Fonts, MDI codepoints, LVGL theme, Now Playing layout | `esphome/music-bar.base.yaml` |
| The artwork traps (byte order, alpha, re-binding on download) | comments on the `image:` block in the base |
| Build-time station logos, generated radio pages | dropped — the browser is one page rewritten at runtime |
| IMU auto-rotation | not ported yet; it was never confirmed working |
