# The prior build: `hifi-panel`

This project is a rewrite of a private ESPHome config called `hifi-panel` — a
single 63KB YAML file that ran on one Waveshare ESP32-S3-Touch-LCD-3.49 next to
a WiiM streamer. [`plan.md`](plan.md#where-it-came-from) says why the rewrite
exists; this file is the record of what that build actually did and what was
measured while getting it there.

**It describes a different program.** Nothing here is a description of this
repo's firmware, and some of it is deliberately not carried over — the station
list was generated at build time and the logos compiled into flash, which is
the specific thing this repo replaces with runtime favorites. Read it as
evidence, not as documentation: where [`spec.md`](spec.md) marks something
*proven*, this is usually where the measurement came from.

Two things travelled with it and are in this repo:

- [`scripts/gen-radio-stations.py`](../scripts/gen-radio-stations.py) — the
  build-time station generator, kept because it is the working reference for
  how to read the radio library out of Music Assistant and which artwork
  actually resolves. It writes into the prior build's YAML and does not apply
  to this firmware.
- The LVGL and touch findings, collected under
  [Lessons for the next LVGL + touch device](#lessons-for-the-next-lvgl--touch-device)
  at the end.

---

## Hardware & network

- **Board**: Waveshare ESP32-S3-Touch-LCD-3.49 — AXS15231B QSPI display +
  capacitive touch (same chip drives both), native panel is 172×640
  (portrait), mounted physically rotated 90° for a landscape 640×172 "bar"
  next to the hifi. Mains-powered (no battery/IMU/audio wired up).
- **Network**: `hifi-panel.local` / `192.168.1.87`, joined to the `X9-2G` 2.4GHz
  IoT WiFi (per the fleet convention — see `IOT_WIFI_SSID` in `secrets.yaml`).
- **HA entities**: `device_tracker.hifi_panel`, `sensor.hifi_panel_ip_address`,
  `binary_sensor.hifi_panel_status`, `light.hifi_panel_backlight`.
- **Config**: `/config/esphome/hifi-panel.yaml` on the `homeassistant` host —
  see `docs/esphome-devices.md` for the general build/flash workflow.

## What it does

Four-page LVGL touch UI:

1. **Now Playing** — a 152×152 album/station artwork tile on the left, three
   text lines to its right (station or album / artist / track, each scrolling
   if long), a row of three 54×52 icon transport buttons (prev / play-pause /
   next), and a full-height accent strip down the right edge that opens the
   radio pages.
2. **Radio 1-4** — four pages of station tiles, five per page: an 84x84 station
   logo on a grey mat (`clickable: false`, or it swallows the tap) with the
   name beneath, chevron edge buttons to page
   between them and back to Now Playing (the page list wraps). Tapping a tile
   plays it and jumps straight back to Now Playing so the choice is visible.

**The radio pages are generated, not hand-written.** Everything between the
`# >>> BEGIN GENERATED …` / `# <<< END GENERATED …` markers in
`hifi-panel.yaml` is emitted by `scripts/esphome/gen-radio-stations.py`. Edit
those blocks and the next run overwrites them. See "Regenerating the station
list" below.

Buttons use Material Design Icons, pulled at build time from the MDI webfont
via ESPHome's `font: file: type: web`. **Verify MDI codepoints against
`Templarian/MaterialDesign-SVG`'s `meta.json` rather than recalling them** —
several sit one digit apart from unrelated icons (`dots-horizontal` is
`F01D8`; `F01D9` is something else entirely).

Layout coordinates were measured off the design mockup by sampling the image
rather than eyeballed: art tile at x=8,y=10 152×152, text column left edge
x=172, transport row y=110 h=52, right strip x=590 w=50. Accent colour
`#0095FF` was sampled from the same mockup.

**Data flow:**
- Now-playing text comes from `sensor.living_room_media_title` / `_artist` /
  `_media_status` / `_input` / `_station` — the same flat sensors
  `hifi-receiver.yaml` (the LED scroller near the same hifi) already reads;
  see that file + HA `configuration.yaml` template sensors for how they're
  derived from the WiiM/Music Assistant entity stack. `_station` is the big
  top line and comes from `media_album_name`, which Music Assistant sets to
  the station name for radio and the album name for everything else.
- Artwork comes from `sensor.living_room_art_url` — a deliberately *bounded*
  URL, see "Album art" below. This is the one thing on the panel that fetches
  over the network at runtime.
- Transport buttons deliberately target **two different entities**.
  `media_player.wiim_living_room` does **not** advertise `PREVIOUS_TRACK` or
  `NEXT_TRACK` (`supported_features=154127` — bits 16 and 32 are clear), so
  HA rejects those calls and the buttons look dead while play/pause still
  works, because it *does* advertise `PAUSE`. Skip therefore goes to
  `media_player.living_room_3` (the Music Assistant queue view,
  `supported_features=8322623`), which supports both. Play/pause stays on the
  WiiM: that is the physical device and works for every input, whereas the MA
  entity only controls its own queue, so routing pause there would break
  Bluetooth / Line In / Optical. See `reference_ha_living_room_now_playing`
  memory for the wider entity topology.
  *(Observed: `media_next_track` on the MA entity advances reliably;
  `media_previous_track` is accepted but does not always walk back a track —
  that is MA queue behaviour, not a config issue.)*
- Station tiles call `music_assistant.play_media` on
  `media_player.living_room_3` with the station's stable `library://radio/N`
  URI. They no longer go through `input_select.radio_station` or the
  `radio_play_selected_station` automation.
- The station list and its logos are generated from Music Assistant's API —
  see "Regenerating the station list" below. Station logos are compiled into
  flash at build time and cost no RAM; the only image fetched at runtime is
  the now-playing artwork.

**Home Assistant setup requirement**: the "Allow the device to perform Home
Assistant actions" toggle (Settings → Devices & Services → ESPHome → HiFi
Panel → device page → gear icon) must be **on**, or every
`homeassistant.action` call silently no-ops — no error anywhere, buttons
visually respond (LVGL press state) but nothing happens on the WiiM. This
toggle defaults off on newer HA versions. Cost about half the debugging
session to find.

## Architecture notes / gotchas for the next LVGL+touch device

See `docs/esphome-devices.md`'s general ESPHome notes for the reusable
lessons (global `lvgl: rotation:`, the AXS15231 touch transform, `component.
update` warm-up delay, `scrollable: false` requirement). This file only
covers what's hifi-panel-specific.

## Album art (working — but only because the URL is bounded server-side)

An earlier attempt at artwork crash-looped the device and was reverted. It now
works, and the reason is worth understanding before touching it: **nothing
about the device side got safer — the URL it is given did.**

Artwork is a single `online_image` slot fed from `sensor.living_room_art_url`,
an HA template sensor that only ever emits a Music Assistant image-proxy URL
with `?size=160&fmt=png`, or a size-pinned Spotify CDN URL, and emits an empty
string otherwise. There are two `online_image` instances — one per format, see
"Spotify Connect" below — but only one image on screen, and the station logos
on the radio pages are static and compiled into flash rather than fetched.

Measured result: **13,000 bytes, 152×152, ~261 ms** download-plus-decode,
versus the 2331 ms of blocking decode logged by the original version.

### The three failure modes and what actually fixes each

1. **Decode cost scales with *source* pixels, not the 152px slot it is drawn
   into.** `resize:` does not help — it only sets the destination buffer.
   JPEGDEC's draw callback walks every source pixel one at a time and
   `runtime_image/image_decoder.cpp`'s `ImageDecoder::draw()` applies the
   scale factor *per pixel*. A 1200×1200 cover is 1.44M callbacks to fill a
   152×152 tile; a 160×160 source is 25.6k, about 1.8% of the work.
   *Fix:* `?size=160`, so Music Assistant LANCZOS-downscales server-side
   (`helpers/images.py`: `img.thumbnail((size, size), Image.Resampling.LANCZOS)`)
   and the device never sees more than 160×160.

2. **`format:` is fixed at compile time, and `AUTO` does not exist** in
   2026.7.3 — the registry is `BMP/JPEG/PNG/JPG` only, though esphome.io's
   docs list `AUTO` (the docs are ahead of this version). *Fix:* `?fmt=png`
   plus `format: PNG`. Note **`fmt=jpeg` would not be safe**: Music Assistant
   silently returns PNG instead when the source has an alpha channel
   (`if target_format == "JPEG" and _has_alpha(img): ... target_format = "PNG"`),
   which is common for radio logos — the device would get a PNG through a JPEG
   decoder. PNG also streams through pngle, so unlike JPEG it never buffers
   the whole file (`online_image.cpp:128` resizes the download buffer to the
   full content-length for JPEG only, which is how a ~750KB cover became a
   ~750KB contiguous allocation).

3. **Raw upstream `entity_picture` URLs are unbounded.** This is the one that
   actually bit, and it is still live upstream: `media_player.living_room_3`
   alternates between the proxied form and handing out the origin URL directly
   (observed: `kingdubfamily.com/wp-content/uploads/.../download-150x150.png`).
   Archive.org art has been seen at ~750KB via this path. *Fix:* the template
   sensor requires `/imageproxy/` to appear in the URL and falls back to
   `media_player.wiim_living_room` (which is reliably proxied) — it never
   passes an unproxied URL through, and returns empty rather than guess.

### Spotify Connect needs a second, JPEG slot

When Spotify Connect streams straight to the WiiM, **Music Assistant has no
library item for the track** — its queue `current_item` is literally
`"Music Assistant Spotify Connect"` — so there is no `proxy_id` and nothing to
route through the image proxy. `media_player.wiim_living_room` reports MA's own
logo as `entity_picture` in that state, which is useless. The only real artwork
is Spotify's own CDN JPEG on `i.scdn.co`.

Because `format:` is fixed at compile time and cannot be switched at runtime,
that needs its own `online_image` instance (`art_jpg`, `format: JPEG`).
`refresh_art` routes by URL shape — `/imageproxy/` goes to the PNG slot,
anything else to the JPEG slot — and both handlers point the *same* LVGL widget
at whichever decoded, so there is still only one image on screen.

Bounding still applies. Spotify encodes the size in the image-id prefix, and
the HA sensor pins it to the 300px variant:

| token | size | bytes |
|---|---|---|
| `ab67616d00004851` | 64px | 1,542 |
| `ab67616d00001e02` | **300px (used)** | 11,582 |
| `ab67616d0000b273` | 640px | 41,145 |

Measured on-device: ~588 ms for the TLS handshake plus download, then ~592 ms
to decode. Noticeably slower than the ~261 ms of a proxied 160px PNG — a
300×300 JPEG is 3.5× the pixels and DCT decoding costs more per pixel than
pngle. It is a one-off stall on track change, not a loop, but if it ever needs
to be cheaper the 64px token is the lever (at the cost of a very soft image in
a 152px slot).

**This is why `http_request` sets `verify_ssl: false`.** Everything else the
panel fetches is plain HTTP on the LAN; the Spotify CDN is HTTPS. Validating
certificates would pull in a CA bundle and the memory to check against it, for
public read-only album art on a device that already refuses any URL the HA
sensor has not vetted.

### Constraints on the Music Assistant image proxy

- Allowed `size` values are a discrete set — **80 / 160 / 256 / 512 work; 128,
  150, 172, 200 and 1200 all return HTTP 400.** 160 is the closest to the
  152px slot.
- It **never upscales** (`PIL.Image.thumbnail` semantics), so a 150×150 source
  comes back 150×150 regardless of the requested size.
- It only accepts **its own content hashes** — `?path=` and `?url=` forms
  return 400, so it cannot be used to launder an arbitrary third-party URL.
  If artwork ever needs to come from a source MA has not hashed, that needs a
  separate resize proxy rather than a tweak here.
- Re-encoding is PIL with no `progressive=True`, so output is baseline JPEG /
  non-interlaced PNG. This matters because the decoder rejects progressive
  JPEG outright (`JPEG_MODE_PROGRESSIVE` → "Unsupported JPEG image").

### Two things that make a decoded image render as a blank tile

Both of these produce a perfectly successful-looking log — `Decoding complete:
152x152`, `art: decoded ok` — while the screen shows nothing. Don't trust the
decode log as evidence that the picture is on screen.

- **LVGL caches the image source, and binds it before the buffer exists.**
  `lv_image_set_src()` calls `lv_image_decoder_get_info()` once and keeps the
  result. At setup time an `online_image` buffer is still null with
  width/height 0, so that call fails and LVGL runs `reset_image_attributes()`
  — the widget ends up with *no source at all*, permanently. Nothing in
  `online_image`/`runtime_image` invalidates LVGL's cache (grep either
  component for "lvgl" — no hits), so the src must be re-set after the
  download:
  ```yaml
  on_download_finished:
    - lvgl.image.update: { id: img_art, src: art_img }
  ```
- **Leave `byte_order` alone — do NOT set `BIG_ENDIAN`.** The generated
  `lv_conf.h` sets `LV_COLOR_16_SWAP 1`, which reads like "image data is
  big-endian". It is not. `lv_color16_t` is declared plain
  `blue:5, green:6, red:5` with no reference to that macro, and
  `LV_COLOR_16_SWAP` is used in exactly one place in all of LVGL —
  `lv_refr.c`, calling `lv_draw_sw_rgb565_swap()` immediately before
  `flush_cb`. It swaps bytes on the way *out to the panel*, long after image
  data is read. Setting `BIG_ENDIAN` byte-swaps every pixel:

  | logo | real colour | renders as |
  |---|---|---|
  | CRB Boston | teal `(0,126,145)` | orange `(246,64,24)` |
  | Fréquence K | cyan `(5,160,220)` | green `(24,97,41)` |
  | King Dub | pure black & white | **unchanged** |

  That last row is the trap: pure black and white are invariant under a
  RGB565 byte swap, so a monochrome logo looks perfectly correct either way.
  Never use one to verify byte order — test with a saturated colour.

### Transparent station logos

Most radio logos are PNGs with a transparent background, and they come in
**both polarities** — WWOZ is white-on-transparent, Radio Meuh is
black-on-transparent. Two things follow.

**`transparency: ALPHA_CHANNEL` is required, not optional.** With the default
`opaque`, `draw_pixel()` writes `color_to_565(color)` and ignores alpha
entirely, so whatever RGB happens to sit *under* a fully-transparent pixel
gets painted. That RGB is undefined and encoder-specific — which is exactly
why transparent backgrounds came out green on one logo and orange on another
while others looked fine. `ALPHA_CHANNEL` stores the alpha plane instead
(`LV_COLOR_FORMAT_RGB565A8`) so LVGL composites properly. It costs `w*h`
extra bytes: the buffer goes from 46,208 to **69,312** for a 152×152 tile.

**Music Assistant cannot flatten it for us.** Its thumbnail generator *does*
have a `flatten_transparency` path that composites onto white, but
`handle_imageproxy()` calls `_serve_thumbnail(path, provider, size,
image_format)` without that argument — so the HTTP endpoint always leaves
alpha intact, and only internal callers (airplay) can request flattening.
There is no query parameter for it.

**The tile background is therefore load-bearing.** Because logos come in both
polarities, no single background works for all of them: black hides
white-on-transparent, white hides black-on-transparent. The tile sits at
`#111111` while idle and switches to `#808080` once artwork loads — mid-grey
keeps white at ~3.9:1 and black at ~5.3:1 contrast. Fully-opaque artwork
covers the tile completely, so the grey only ever shows behind logos that
actually have transparency. If one polarity dominates in practice, shifting
that value is the knob to turn.

### Device-side details worth keeping

- `update_interval: never` means `online_image` **never auto-fetches** — it
  only downloads on an explicit `component.update:` or `online_image.set_url`.
- Art fetching is gated behind an `art_ready` global set 12s after boot, so
  nothing hits the network during the startup window. The original version
  kicked downloads off from `on_boot` and its first few steps silently
  no-op'd; deferring removes that whole class of race.
- The refresh script dedupes on the last-fetched URL and normalises HA's
  literal `unavailable` / `unknown` states to empty. Without both, a template
  reload produced `URL must start with http:// or https://` and a second
  push landed mid-download ("Image already being updated").
- The dedupe is deliberately *two separate `if`s*, not `if/else`: a repeat
  push of the same URL must be a no-op, not a reason to tear the artwork down
  and show the placeholder.
- **Dedup compares path+query, not the whole URL, and against what is on
  screen rather than what was last requested.** Two separate problems, both
  seen in the logs:
  - Music Assistant answers on **more than one port** (`:8095` and `:8097`)
    and HA alternates `entity_picture` between them, so identical artwork
    arrives as two different URLs within the same second. Comparing whole
    URLs fired a second fetch that `online_image` then rejected with
    *"Image already being updated"*.
  - That rejection has no callback, but the request had **already advanced
    `last_art_url`**. The 60s reconcile then compared equal and never
    retried, so the thumbnail stuck on the previous image while the text was
    correct. Tracking `shown_art_url` (set in `on_download_finished`, cleared
    in `on_error`) makes a dropped request self-heal within one reconcile.

- **Failed fetches retry a bounded number of times, then stop.** Clearing
  `shown_art_url` on error makes the reconcile retry — right for a transient
  failure, wrong for a permanent one. Music Assistant returns a `proxy_id`
  even when it holds no artwork and the proxy 404s for those, so a station
  with no image produced a 404 every 60 seconds indefinitely. Note that
  **every artwork-less station collides on one sentinel proxy_id** (it is
  `sha256(provider + "/" + "")`, and the path is empty for all of them), so
  this is not a per-station quirk. After three attempts the URL is marked
  handled and left alone until it changes.

  Worth knowing when diagnosing this: a track change *within the same album*
  legitimately produces no artwork change — same cover, same URL — so
  "thumbnail didn't update" is only a bug if the **album** changed.
- **A 60s `interval:` re-runs `refresh_art` (and `refresh_now_playing`) as a
  self-healing reconcile.** HA only pushes the art URL on *change*, so a
  single missed push leaves a stale placeholder until the station next
  changes — which on radio can be hours. This was observed in practice: on
  one boot HA delivered the URL before `art_ready` flipped at +12s, and
  nothing fetched until the value next changed. Because `refresh_art` dedupes
  on `last_art_url`, the reconcile is a no-op in the steady state and never
  re-downloads; it only acts when the display has actually drifted from HA.
  It also covers HA restarts and Wi-Fi drops spanning a change.

## Auto-rotation from the IMU

The board carries a **QMI8658** 6-axis IMU at `0x6b` on a *second* I²C bus —
`GPIO47/48`, per Waveshare's `user_config.h` (`ESP_SDA_NUM` / `ESP_SCL_NUM`).
It is not on the touch bus, which is why the original `i2c:` scan only ever
found `0x3b`. A PCF85063 RTC also lives there at `0x51`, unused.

> **Status (2026-08-08): implemented but unverified.** A completed rotation
> has never been observed. Read this section as a design record, not as a
> working feature, until someone confirms it on the hardware.

Measured upright, this panel reads **Accel Y = −0.99 G** — gravity sits almost
entirely on −Y, so the *sign of Y* should be the whole orientation signal.

What is actually established:

| claim | evidence |
|---|---|
| IMU is present and readable | QMI8658 answers at `0x6b` on `GPIO47/48`; steady readings |
| Y is the candidate flip axis | gravity sits on −Y at −0.99 G upright — an inference from where gravity sits, **not** a proven flip axis |
| a flip does cross the threshold | during a hands-on test Y swung to **+0.92 G**, well past ±0.4 G |
| the screen rotates | **not shown.** On that test the debounce was 2 samples at a 5 s poll, so the single +0.92 G sample was correctly discarded and nothing happened. The timing was changed afterwards but never retested |

If it still does not flip, try **Z instead of Y** — `accel_z` is already wired
up for exactly that. A rotation about a different body axis would move Z.

Three things keep it from being twitchy:

- **±0.4 G dead band.** Laid flat or carried, Y is near zero and nothing
  happens; only a decisive orientation counts.
- **Three consecutive agreeing readings at a 1 s poll (~3 s)** before a flip
  is applied, so a knock or a lift-and-reposition cannot rotate the UI
  mid-gesture. Getting this balance wrong is easy in the unhelpful direction:
  a first attempt used 2 samples at a 5 s poll, which needed the panel held
  upside down for 10-15 s. A real flip test showed Y swinging to **+0.92 G**
  for a single sample and then back — detected correctly, debounced away, and
  indistinguishable from "it doesn't work". The sensors are `internal: true`,
  so polling every second costs no HA traffic; the thing worth avoiding is
  *publishing* at that rate, not sampling.
- **`rot_flipped` is persisted** (`restore_value: true`) and re-applied in
  `on_boot`, so a reboot comes back the way the panel is actually sitting
  instead of flashing to the default and correcting itself.

`lvgl.display.set_rotation` is a genuine **runtime** action — it calls
`set_resolution_()`, `update_orientation_()` and invalidates the screen — and
`LvglComponent::rotate_coordinates()` reads `rotation_` live, so **touch
hit-testing follows the flip with no extra work**. The only requirement is
that rotation was enabled at setup (it is: `lvgl: rotation: 90°`); otherwise
`set_rotation` logs *"Display rotation cannot be changed unless rotation was
enabled during setup"* and does nothing.

**Sample fast, publish never.** Both axis sensors are `internal: true`, so a
1 s poll costs no HA traffic and no log noise — the thing worth avoiding is
*publishing* five sensors every second, not sampling. Getting that backwards
is what produced the 5 s poll that made the feature look broken.

## Regenerating the station list

```bash
scripts/esphome/gen-radio-stations.py --config /tmp/esphome-build/hifi-panel.yaml
esphome run hifi-panel.yaml --device 192.168.1.87 --no-logs
```

The script reads the radio library straight from Music Assistant's API
(`music/radios/library_items`, needs `MA_API_TOKEN` in `secrets.yaml` — create
one in the MA UI under Settings → Profile) and rewrites two marked blocks.

Three design decisions worth keeping:

- **Stations play by URI, not by name.** Tiles call
  `music_assistant.play_media` with `library://radio/N` directly. Before this,
  the station list was hardcoded in *three* places that all had to agree on
  display strings: this config, the `input_select.radio_station` options, and a
  name→URI map inside the `radio_play_selected_station` automation. Changing a
  favourite meant editing all three. Now it is one command. The `input_select`
  and that automation are no longer on the panel's path (they still work for
  anything else that uses them).
- **Logos are compiled into flash, not fetched at runtime.** ESPHome's
  `image:` `file:` accepts a URL and downloads at *build* time, so a logo costs
  flash and **no RAM** — measured: adding 9 logos moved flash 1,297,760 →
  1,396,635 bytes but RAM only 116,691 → 118,187. A runtime `online_image` per
  tile would instead need its own PSRAM buffer plus a fetch and decode each.
  The trade is a reflash when favourites change, which the script makes cheap.
- **`proxy_id != null` is not a "has artwork" test.** MA returns a `proxy_id`
  even when it holds no image, and the proxy 404s for those. The script
  therefore *fetches* each logo to decide, and falls back to a radio glyph on
  the tile when it doesn't resolve.

Current state: **9 of 16 stations have usable artwork.** The other seven split
into two groups, both fixable in Music Assistant rather than here:

| cause | stations |
|---|---|
| no artwork in MA (`path` is empty) | Big Blue Swing, France Musique, Radio 3FACH, Radio Zinzine, WKCR 89.9 |
| origin URL dead | TSF Jazz (Wikimedia `400: Use thumbnail sizes list`), WKCR (Firebase `402: Payment Required`) |

Note the proxy does **not** rescue a dead origin — MA fetches on demand and
caches on success, so if the origin is gone and nothing was cached, the proxy
404s too.

## Sampled reality of the station logo library

Useful when reasoning about how any of this will behave — measured across the
logos actually in use, fetched through the proxy at `?size=160&fmt=png`:

| property | finding |
|---|---|
| genuinely transparent | 2 of 6 (~50% and ~70% transparent), both with RGB `(0,0,0)` underneath and dark artwork |
| fully opaque | 4 of 6, with real coloured backgrounds (teal, cyan, near-white, near-black) |
| smaller than the 152px slot | common — sources of 57×57 and 150×150 seen, and MA never upscales, so they render soft |
| non-square | yes (160×138, 160×76) — the tile must not assume square |

The practical consequence: most "background colour" problems are *not*
transparency problems, they are the logo's own background. Check whether an
image is actually transparent before reaching for an alpha fix.

## Recovering the device if it drops off the network

The panel is mains-powered next to the hifi and is normally updated over OTA.
If a flash leaves it unreachable, **the UI running fine while the device is
invisible to the network means WiFi, not a crash** — check that before
assuming the worst. Power-cycling it via USB is the recovery, and USB also
gives back a serial console (`ls /dev/cu.usbmodem*`) for the case where it
genuinely is crashing.

One specific way to cause this: building with a placeholder `secrets.yaml`.
`wifi_ssid` / `wifi_password` are baked into the binary at compile time, so a
stub value produces firmware that runs perfectly and cannot join the network —
and OTA is then unavailable to fix it. Confirm with
`strings <build>/hifi-panel.bin | grep -c <expected-ssid>` before flashing, or
just check `secrets.yaml` first. See `docs/esphome-devices.md`.
