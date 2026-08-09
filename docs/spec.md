# ma-bar-3.49 — design spec

What the panel is, what it depends on, and the decisions that shape it. Claims
marked **proven** were measured on hardware, probed against a live Music
Assistant instance, or read out of the ESPHome source at the cited location.
Claims marked **unverified** have a named probe in
[Open questions](#10-open-questions) and should not be built on until it passes.

## 1. Scope

A 640×172 touch bar showing Music Assistant's current playback, with transport
controls and a paged browser for library items. Two hard dependencies, and the
project is deliberately not abstracted away from either:

**The board.** Waveshare ESP32-S3-Touch-LCD-3.49. The AXS15231B drives display
and touch from one chip over QSPI; the pin map, the QSPI init sequence and the
172×640 native geometry are all board-specific. The QMI8658 IMU sits on a
*second* I²C bus at GPIO47/48, which is why an I²C scan of the touch bus never
finds it. 16MB flash, octal PSRAM at 80MHz — the framebuffer needs it.

**Music Assistant.** The panel uses MA's library API for the item list, MA's
image proxy for artwork, and `music_assistant.play_media` for playback. It
never addresses a speaker directly, so any player MA supports works unchanged.

Everything the panel displays arrives at runtime. Changing your favorites, or
what the browser shows, never requires a rebuild or a reflash — see
[§7](#7-runtime-architecture). This is the central design goal and it
constrains most of what follows.

Three pieces make that work: the ESPHome config on the device, a Home Assistant
package that resolves items and pushes pages, and a small artwork normalizer
that guarantees every image arrives at identical dimensions. [§4](#4-artwork)
explains why the third one is not optional.

## 2. Screen layout

The bar is short and wide, which drives the whole UI. Two kinds of page:

**Now Playing** — a square artwork tile on the left, three text lines beside it
(album or station / artist / track, each scrolling when too long), a row of
icon transport buttons, and a full-height strip down the right edge that opens
the browser.

**Browser** — a page of five tiles across, each an artwork square on a mat with
the item name beneath, plus chevron edge buttons to page through. Tapping a
tile plays it and returns to Now Playing so the choice is visible. Five across
rather than six leaves the name enough width to wrap to two readable lines.

There is exactly **one** browser page in the LVGL layout, holding five tile
widgets. LVGL widgets in ESPHome are created at compile time and cannot be
added at runtime, so paging means rewriting those five tiles rather than
navigating between many pre-built pages. That is what keeps the browser
independent of how many items you have.

## 3. Items are chosen by name

Configuration refers to items by **name**, not by ID.

Music Assistant's own `library://radio/17` style URIs are stable inside one MA
instance, but they are database row IDs: they mean nothing on anyone else's
install, and they move if a library is rebuilt. Underneath them sit provider
IDs which are worse — **proven**: every radio item on the reference instance
carries `provider_mappings[].provider_domain: "radiobrowser"` with an upstream
UUID, and radio-browser.info's entries change without the listener's
involvement or consent.

Names are the thing the user typed, the thing on screen, and the thing that
survives both. Resolution to a URI happens in Home Assistant at the moment a
page is built, so a rebuilt library corrects itself on the next page turn.

**Proven**: MA's `music/search` command resolves `"WKCR"` → `library://radio/17`.
Home Assistant exposes the same thing as `music_assistant.search`, a response
service taking `name` and `media_type`.

Two consequences to handle:

- Names must be unique within a media type. A config entry may carry an
  explicit `uri:` that overrides lookup, as the tiebreak for a genuine clash.
- A name that resolves to nothing renders as a tile marked unresolved rather
  than vanishing. A silently missing tile is a gap the user has to notice.

## 4. Artwork

### The constraint that shapes everything

ESPHome allocates a runtime image's pixel buffer lazily, sized to the decoded
image, and **frees and reallocates it whenever the decoded dimensions change**.
**Proven** in `runtime_image.cpp`: `resize_buffer_()` returns early only when
`buffer_width_` and `buffer_height_` both match, and otherwise calls
`release_buffer_()` before allocating again. Its failure message reports the
largest free block, not the free total — the failure mode is fragmentation.

A `resize: 84x84` does not prevent this. **Proven** in `RuntimeImage::resize()`:
with both dimensions fixed it computes one uniform scale factor and preserves
aspect ratio, so the buffer takes the *source's* shape. Music Assistant's
artwork is frequently not square and never upscaled — 57×57, 150×150, 160×138
and 160×76 were all observed in one small station library — which under
`resize: 84x84` yields buffers of 84×84, 84×84, 84×72 and 84×39 respectively.

Five tile slots turning over on every page turn, each reallocating to a
different shape, is a fragmentation engine. This is the mechanism behind the
"PSRAM pressure" that made the prior build abandon its twelve-concurrent-image
design and retreat to build-time logos in flash.

The fix is to stop the dimensions from varying. If every URL returns exactly
the tile size, each slot allocates its buffer once on first use and reuses it
forever — no frees, no fragmentation, and the whole live design becomes safe.

### The normalizer

So artwork does not come from Music Assistant directly. It comes from a small
service that returns **exactly `N×N` PNG, always**, and resolves in this order:

1. **A user override**, if one exists for that item
2. **Music Assistant's image proxy**, if it actually returns an image
3. **A generated placeholder** for the media type

Non-square sources are padded rather than cropped, onto the same mat colour the
tile uses, so padding is invisible. Results are cached by slug.

This placement earns its keep several times over:

- Dimensions are guaranteed, which is the requirement above.
- The "does artwork exist" test happens where it can: **proven**, a `proxy_id`
  is returned even when there is no artwork — a reference radio item has
  `images: [{path: "", proxy_id: "3a47…", remotely_accessible: true}]` and the
  proxy 404s for it. Only a real fetch tells you, and the device should not be
  the thing making that discovery mid-page-turn.
- Overrides need no existence check on the device and no failed round trip.
- Transparency is flattened onto the mat server-side, which MA cannot do —
  its proxy handler does not expose the flatten argument.
- Artwork from outside MA becomes possible at all. MA's proxy only accepts its
  own content hashes, so arbitrary third-party URLs have nowhere else to go.

Implemented in `scripts/normalize-artwork.py`. **Proven** against the reference
library: 20 items across two sections produced 20 files at one distinct
`(84, 84) RGB`, 14 sourced from MA and 6 generated, 108KB on disk in total. A
deliberately awkward override — 1400×520 with an alpha channel — came out at
84×84 RGB like everything else.

Three details the first run settled:

- **Nothing is ever blank.** An item with no artwork anywhere gets a monogram:
  its initials on a background whose hue is hashed from its name. Deterministic,
  so an item keeps its colour between runs, and distinct, so a page of them
  reads as a design rather than as five identical failure icons.
- **Corners are rounded, to the mat colour.** Most logos turn out to be opaque
  with backgrounds of their own — frequently white — so on a dark UI a grid of
  raw squares reads as mismatched rectangles. A shared rounded edge makes them
  one set of cards. Insetting the artwork instead does *not* work: on an opaque
  logo it shrinks the logo's own background too, leaving a sharp-cornered square
  floating inside the rounded card.
- **Every tile is fingerprinted.** The manifest carries a short content hash per
  item, and Home Assistant appends it to the URL. The device refetches only when
  a URL changes, and a normalized filename never changes, so without the hash a
  swapped override would go unnoticed until reboot. With it, replacing an image
  and rerunning the normalizer is enough.

Two placements, both viable:

**Pre-rendered (recommended).** A script normalizes every item in the
configured sections into a directory Home Assistant already serves —
`<ha-config>/www/ma-bar/` at `http://<ha>:8123/local/ma-bar/`. It reruns on a
timer or when the library changes. The device fetches plain static files, there
is no service to keep alive, and page turns never wait on a resize.

**Live proxy.** The same logic behind an HTTP endpoint, resizing on demand. One
more thing to run, but nothing to invalidate.

Either way the device only ever sees `<base>/<slug>.png`, and the base URL is
configuration.

### What is still true of MA's proxy

The normalizer fetches from MA at `?size=256&fmt=png`, never from the raw
`path` in the API response — those are origin URLs of arbitrary size and
format, and some are already dead. Sizes 80/160/256/512 only, never upscaled.

PNG rather than JPEG, for two reasons that both still apply: ESPHome fixes an
image's `format:` at compile time, and MA silently returns PNG anyway when a
source has an alpha channel, which is common for logos. PNG also streams
through pngle instead of buffering the whole file.

Bounding the source remains the only thing that reduces decode cost — it scales
with source pixels, not with the slot on screen. **Proven**: a 1200px cover
logged 2331 ms of blocking decode; the same image at `?size=160` took ~261 ms.
With the normalizer that bound is enforced twice, which is fine.

### Two rendering traps

Both produce a *successfully decoded* image that still looks wrong, so a clean
decode log proves nothing about what is on screen.

- **LVGL binds an image source at setup**, when the buffer is still null.
  `lv_image_set_src` calls `lv_image_decoder_get_info`, that fails, and
  `reset_image_attributes()` leaves the widget with no source permanently. Every
  slot must re-bind in `on_download_finished:` via `lvgl.image.update:`.
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
`music_assistant.get_library` with `media_type`, `favorite`, `search`,
`order_by` and `pagination`. Playback is uniform across types — `play_media`
with a `media_type` — so a favorite playlist is no harder to put on a tile than
a radio station.

That `pagination` argument matters: it means a page turn is one service call
for five items, not a full library fetch that Home Assistant then slices.

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

Sections concatenate into one virtual list that the browser pages through.

## 6. The Home Assistant contract

Home Assistant holds all the logic. The device holds none of it, which is what
lets the browser change without a rebuild.

**Now playing** reaches the device as flat sensors — title, artist,
album-or-station, playback state, artwork URL — rather than as a media player
entity, because the useful fields are scattered across MA's entity model and
template logic belongs in Home Assistant, not in device YAML. This repo ships
those templates as an installable package.

**The browser** is a request/response pair:

- The device asks, by calling a Home Assistant script with a page index.
- Home Assistant answers, by calling back into the device's native API with the
  five names, five artwork URLs and five URIs for that page, plus how many
  pages exist.

**Proven** in `api/__init__.py`: user-defined API actions accept `string[]`,
`int[]`, `float[]` and `bool[]` argument types, so one call carries a whole
page. Two things about how they are passed:

- Arrays arrive as `FixedVector<T> const&`, a **non-owning view into the receive
  buffer**, which is reused as soon as the synchronous part of the handler
  returns. The handler must copy into globals immediately rather than holding
  the reference.
- If the handler contains anything non-synchronous — `delay`, `wait_until`,
  `script.wait` — ESPHome switches that action to owning `std::vector` types.
  Keeping the handler synchronous is the simpler contract.

One live-instance quirk to absorb: **proven**, MA answers on two ports (8095
and 8097) and Home Assistant alternates `entity_picture` between them, so
identical artwork arrives as two different URLs seconds apart. Any
de-duplication compares path and query only, and compares against the URL
currently *on screen* rather than the last one requested — ESPHome's
`online_image` silently drops an update while a download is in flight, so a
requested-URL variable can advance without anything having changed.

## 7. Runtime architecture

Five tile widgets and six image slots, all fixed at compile time; everything
else is data.

A page turn goes: device calls the Home Assistant script → script queries MA
with `pagination` → script calls the device's API action with three arrays →
device copies them into globals, writes the five labels, and points the five
tile image slots at their URLs via `online_image.set_url` → each slot re-binds
its LVGL widget in `on_download_finished`.

Labels land immediately; artwork arrives as it downloads. The sixth image slot
is the Now Playing thumbnail, which is independent.

Because every URL returns the same `N×N`, each slot allocates once on first use
and never reallocates. That is the whole reason this is safe to do at runtime,
and it is a property of the normalizer rather than of the device config — if a
differently-sized image ever reaches a slot, the fragmentation described in §4
comes back.

Two things still need measuring before this is settled: the PSRAM cost of six
concurrent slots alongside the framebuffer, and whether five parallel fetches
plus decodes make a page turn feel slow. Both probes are in §10. If page turns
do drag, the fallback is to reuse the prior build's proven approach for a
subset — build-time logos in flash, which cost **proven** 98KB of flash and
1.5KB of RAM for nine images — as a static first section, with live pages
behind it.

## 8. Prerequisites

Before any of this works on a given install:

- **ESPHome 2026.5 or newer.** The panel uses a global `lvgl: rotation: 90°`
  with the display and touchscreen left native. Current ESPHome rotates LVGL
  hit-testing internally to match; earlier versions do not. The raw
  `touchscreen: on_touch` trigger still reports un-rotated coordinates, which
  is expected rather than a bug. Developed against 2026.7.3.
- **Home Assistant's per-device action toggle must be on.** Settings → Devices
  & Services → ESPHome → *device* → gear → "Allow the device to perform Home
  Assistant actions". It defaults off on recent Home Assistant and silently
  no-ops every service call with no error logged anywhere: buttons visibly
  react and nothing happens. Check this before suspecting a config bug.
- **A Music Assistant long-lived token**, created in the MA UI under Settings →
  Profile. The token embedded in Home Assistant's `music_assistant` config
  entry is a different credential and does not authenticate against MA's own
  API port.
- **Somewhere to run the normalizer**, with Pillow. Any host that can reach MA
  and write to Home Assistant's `www` folder.
- **Correct MDI codepoints.** Icon glyphs are pulled from the Material Design
  Icons webfont at build time. Verify codepoints against `meta.json` in
  `Templarian/MaterialDesign-SVG`; several sit one digit from unrelated icons.

## 9. Known LVGL trap

A plain `obj` nested inside a button swallows presses: LVGL sets
`LV_OBJ_FLAG_CLICKABLE` by default on `obj`, while `label` and `image` both
remove it. In the prior build this made the grey mat behind each logo eat every
tap on the artwork, leaving only the name tappable. Decorative containers need
`clickable: false`.

## 10. Open questions

Each needs its probe to pass before the design above depends on it.

- **Does `play_media` accept a bare name?** The service takes `media_id` with an
  `object` selector and carries `artist`/`album` disambiguation fields, which
  implies name search, but this is **unverified** — the probe plays audio in a
  real room. *Probe*: call `music_assistant.play_media` with `media_id: "WKCR"`,
  `media_type: radio` against a test player and check the queue. Costs nothing
  structurally if it fails: pages already carry resolved URIs, so tiles can
  simply play those.
- **What do six concurrent image slots cost?** *Probe*: build with six slots at
  the tile size plus the framebuffer, read the ESPHome heap report, then page
  back and forth thirty times and confirm the largest free block has not moved.
  The second half is the one that matters — total free PSRAM is not the metric.
- **How slow is a page turn?** *Probe*: log the interval from tap to the fifth
  `on_download_finished`, cold and warm. Decide against a target of one second
  to first paint, artwork allowed to trail.
- **Does the IMU auto-rotation actually flip the screen?** **Unverified** in the
  prior build. The IMU reads reliably and `lvgl.display.set_rotation` is a real
  runtime action whose rotation touch input follows, but the screen was never
  observed rotating — the one hands-on test was discarded by a debounce window.
  Gravity is inferred to sit on the Y axis; Z is the untried alternative.
- **Does a tile survive a library rebuild?** The name-based design predicts yes,
  with no user action. *Probe*: rebuild the MA library and turn a page.
