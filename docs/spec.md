# ma-bar-3.49 — design spec

What the panel is, what it depends on, and the decisions that shape it. Claims
marked **proven** were measured on hardware or probed against a live Music
Assistant instance. Claims marked **unverified** have a named probe in
[Open questions](#open-questions) and should not be built on until it passes.

## 1. Scope

A 640×172 touch bar showing Music Assistant's current playback, with transport
controls and a paged browser for library items. Two hard dependencies, and the
project is deliberately not abstracted away from either:

**The board.** Waveshare ESP32-S3-Touch-LCD-3.49. The AXS15231B drives display
and touch from one chip over QSPI; the pin map, the QSPI init sequence and the
172×640 native geometry are all board-specific. The QMI8658 IMU sits on a
*second* I²C bus at GPIO47/48, which is why an I²C scan of the touch bus never
finds it.

**Music Assistant.** The panel uses MA's image proxy for artwork, MA's library
API for the item list, and `music_assistant.play_media` for playback. It never
addresses a speaker directly, so any player MA supports works unchanged.

Home Assistant sits between the two. The panel is an ESPHome device using the
native API, and every value it reads is a flat sensor that Home Assistant
derives — see [§6](#6-the-home-assistant-contract).

## 2. Screen layout

The bar is short and wide, which drives the whole UI. Two kinds of page:

**Now Playing** — a square artwork tile on the left, three text lines beside it
(album or station / artist / track, each scrolling when too long), a row of
icon transport buttons, and a full-height strip down the right edge that opens
the browser.

**Browser** — pages of five tiles across, each an artwork square on a mat with
the item name beneath, plus chevron edge buttons to page through. Tapping a
tile plays it and returns to Now Playing so the choice is visible. Five across
rather than six leaves the name enough width to wrap to two readable lines.

## 3. Items are chosen by name

The configuration file lists items by **name**, not by ID.

Music Assistant's own `library://radio/17` style URIs are stable inside one MA
instance, but they are database row IDs: they mean nothing on anyone else's
install, and they move if a library is rebuilt. Underneath them sit provider
IDs which are worse — **proven**: every radio item on the reference instance
carries `provider_mappings[].provider_domain: "radiobrowser"` with an upstream
UUID, and radio-browser.info's entries change without the listener's
involvement or consent.

Names are the thing the user typed, the thing on screen, and the thing that
survives both. So the config says `WKCR`, and resolution to a URI happens
during the build.

**Proven**: MA's `music/search` command resolves `"WKCR"` → `library://radio/17`.
Home Assistant exposes the same thing as `music_assistant.search`, a response
service taking `name` and `media_type` — so name resolution is available at
runtime too, not only at build time.

Two consequences to handle:

- Names must be unique within a media type. Each config entry may carry an
  explicit `uri:` that overrides lookup, as the tiebreak for a genuine clash.
- A build fails loudly on a name that resolves to nothing. Silently dropping a
  tile would leave a gap the user has to notice.

## 4. Artwork

Resolution order for any tile, first hit wins:

1. **A user override**, if one exists for that item
2. **Music Assistant's image proxy**, if it actually returns an image
3. **A glyph** for the media type (radio, playlist, album)

### From Music Assistant

Artwork is fetched through MA's proxy at `?size=256&fmt=png`, never from the
raw `path` in the API response — those are origin URLs of arbitrary size and
format, and some are already dead.

Three things here are settled, and all three cost real debugging time to learn:

- **Bounding the source is the only thing that helps.** Decode cost scales with
  source pixels, not with the size of the slot on screen — a `resize:` in
  ESPHome applies the scale factor per source pixel, so it does not reduce the
  work. **Proven**: a 1200px cover logged 2331 ms of blocking decode; the same
  image at `?size=160` took ~261 ms.
- **PNG, not JPEG.** ESPHome fixes the image `format:` at compile time, and MA
  silently returns PNG when a source has an alpha channel — common for station
  logos. PNG also streams through pngle instead of buffering the whole file.
- **A `proxy_id` is not a promise of artwork.** **Proven**: a reference radio
  item returns `images: [{path: "", proxy_id: "3a47…", remotely_accessible: true}]`
  and the proxy 404s for it. The only test that works is fetching the image.

MA's proxy accepts sizes 80/160/256/512 only, never upscales, and only accepts
its own content hashes. Third-party artwork at an arbitrary URL cannot be
routed through it.

### User overrides

Music Assistant's coverage is uneven — on the reference instance 9 of 16
stations had usable artwork — and some of what it does return is a low-quality
scrape. So the panel supports a directory of user-supplied images that both
fills gaps and overrides what MA has.

Location defaults to Home Assistant's own `www` folder, so no extra
infrastructure is needed:

```
<ha-config>/www/ma-bar/<slug>.png   →   http://<ha>:8123/local/ma-bar/<slug>.png
```

The slug is derived from the item name, which keeps overrides aligned with the
name-based config in §3: rename a station in MA and the override follows it.
The base URL is configurable for anyone serving images elsewhere.

Overrides bypass MA's proxy, which means nothing is bounding them
server-side — and an unbounded image is the failure mode that crash-looped the
original build. So the build step validates every override's dimensions and
byte size against the tile it will fill, and fails on anything oversized rather
than shipping it to the device.

### Two rendering traps

Both of these produce a *successfully decoded* image that still looks wrong, so
a clean decode log proves nothing about what is on screen.

- **Transparency.** Logos arrive in both polarities (light-on-transparent and
  dark-on-transparent), so the mat behind the image is load-bearing and sits
  mid-grey. Alpha needs `transparency: ALPHA_CHANNEL`; without it the undefined
  RGB under transparent pixels gets painted, which is why one logo came out
  green and another orange. MA cannot flatten transparency server-side — its
  proxy handler does not expose the flatten argument.
- **Byte order.** Do **not** set `byte_order: BIG_ENDIAN`. The display gives
  `lv_conf.h` a `LV_COLOR_16_SWAP 1`, which looks like it demands big-endian
  images but does not: LVGL uses that macro in exactly one place, swapping on
  the way *out* to the panel after image data is read. Setting it renders teal
  as orange. Pure black-and-white images are invariant under the swap, so a
  monochrome logo cannot be used to check this.

## 5. What the browser shows

Not just radio. **Proven** against the live API: `music/<type>/library_items`
accepts a `favorite: true` filter for radios, playlists, albums, artists and
tracks alike, and Home Assistant exposes the same thing as
`music_assistant.get_library` with `media_type`, `favorite`, `search` and
`order_by`. Playback is uniform across types — `play_media` with a
`media_type` — so a favorite playlist is no harder to put on a tile than a
radio station.

The catch is that "favorites" is only as useful as the user's tagging. On the
reference instance:

| Type | In library | Marked favorite |
|---|---|---|
| Radios | 15 | 1 |
| Playlists | 101 | 5 |
| Albums | 419 | 0 |
| Artists | 469 | 0 |
| Tracks | 500 | 0 |

A panel hardwired to `favorite: true` would show one station there. So the
source is configurable per section, and a config is a list of sections:

- `favorites` — everything of that type marked favorite
- `all` — the whole library for that type, optionally capped and ordered
- an explicit list of names, for a curated set that ignores both

Each section becomes its own run of browser pages. A cap per section keeps a
419-album library from generating a hundred pages of tiles.

## 6. The Home Assistant contract

The panel reads flat sensors rather than a media player entity, because the
useful fields are scattered across MA's entity model and template logic belongs
in Home Assistant, not in device YAML. This repo ships those templates as a
Home Assistant package so the contract is installable rather than described.

The panel needs: title, artist, album-or-station, playback state, and a
**pre-bounded** artwork URL. That last one is the safety boundary — the sensor
emits an MA proxy URL with its size and format pinned, or an override URL that
passed validation, and emits empty otherwise. The device is never handed a URL
it has to trust.

One live-instance quirk to absorb: **proven**, MA answers on two ports (8095
and 8097) and Home Assistant alternates `entity_picture` between them, so
identical artwork arrives as two different URLs seconds apart. Any
de-duplication compares path and query only, and compares against the URL
currently *on screen* rather than the last one requested — ESPHome's
`online_image` silently drops an update while a download is in flight, so a
requested-URL variable can advance without anything having changed.

## 7. Build modes

The browser's tile artwork can come from flash or from the network, and the
tradeoff is sharp enough that both are worth having.

**Baked** (the default, and what the prior build proved). A generator script
resolves names to URIs, fetches and validates artwork, and writes ESPHome
`image:` entries using build-time web fetch. Logos compile into flash and cost
no RAM at runtime — **proven**: adding nine logos moved flash from 1,297,760 to
1,396,635 bytes while RAM moved only 116,691 → 118,187. Nothing is fetched or
decoded while the panel is running. Changing your favorites means regenerating
and reflashing.

**Live** (later). A fixed pool of tile widgets is populated at runtime from
Home Assistant, one `online_image` per visible slot. Favorites change without a
reflash, at the cost of PSRAM and fetch latency on every page turn.

Baked ships first. Live stays a design goal so that nothing in the config
schema or the HA contract forecloses it.

Generated regions are delimited by explicit `# >>> BEGIN GENERATED …` markers
and are overwritten in place on every run, so hand edits inside them do not
survive.

## 8. Prerequisites

Before any of this works on a given install:

- **ESPHome 2026.5 or newer.** The panel uses a global `lvgl: rotation: 90°`
  with the display and touchscreen left native. Current ESPHome rotates LVGL
  hit-testing internally to match; earlier versions do not. The raw
  `touchscreen: on_touch` trigger still reports un-rotated coordinates, which
  is expected rather than a bug.
- **Home Assistant's per-device action toggle must be on.** Settings → Devices
  & Services → ESPHome → *device* → gear → "Allow the device to perform Home
  Assistant actions". It defaults off on recent Home Assistant and silently
  no-ops every service call with no error logged anywhere: buttons visibly
  react and nothing happens. Check this before suspecting a config bug.
- **A Music Assistant long-lived token**, created in the MA UI under Settings →
  Profile. The token embedded in Home Assistant's `music_assistant` config
  entry is a different credential and does not authenticate against MA's own
  API port.
- **Correct MDI codepoints.** Icon glyphs are pulled from the Material Design
  Icons webfont at build time. Verify codepoints against `meta.json` in
  `Templarian/MaterialDesign-SVG`; several sit one digit from unrelated icons.

## 9. Open questions

Each of these needs its probe to pass before the design above depends on it.

- **Does `play_media` accept a bare name?** The service takes `media_id` with an
  `object` selector and carries `artist`/`album` disambiguation fields, which
  implies name search, but this is **unverified** — the probe plays audio in a
  real room, so it was not run during spec writing. *Probe*: call
  `music_assistant.play_media` with `media_id: "WKCR"`, `media_type: radio`
  against a test player and check the queue. If it fails, the fallback costs
  nothing structurally: resolve through `music_assistant.search` first and pass
  the URI it returns.
- **How many runtime `online_image` slots fit?** Live mode needs a number.
  *Probe*: build with 5 slots at 84×84 RGB565 and read the ESPHome heap report,
  then confirm a page turn does not stall the UI.
- **Does the IMU auto-rotation actually flip the screen?** **Unverified** in the
  prior build. The IMU reads reliably and `lvgl.display.set_rotation` is a real
  runtime action whose rotation touch input follows, but the screen was never
  observed rotating — the one hands-on test was discarded by a debounce window.
  Gravity is inferred to sit on the Y axis; Z is the untried alternative.
- **Does a tile survive a library rebuild?** The name-based design predicts yes.
  *Probe*: rebuild the MA library, regenerate, and confirm the emitted URIs
  changed while the config file did not.

## 10. Known LVGL trap

A plain `obj` nested inside a button swallows presses: LVGL sets
`LV_OBJ_FLAG_CLICKABLE` by default on `obj`, while `label` and `image` both
remove it. In the prior build this made the grey mat behind each logo eat every
tap on the artwork, leaving only the name tappable. Decorative containers need
`clickable: false`.
