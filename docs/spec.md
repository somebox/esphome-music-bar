# esphome-music-bar — design spec

What the panel is, what it depends on, and the decisions that shape it. Claims
marked **proven** were measured on hardware, probed against a live Music
Assistant instance, or read out of the ESPHome source at the cited location.
Claims marked **unverified** have a named probe in
[Open questions](#10-open-questions) and should not be built on until it passes.

## 1. Scope

**A quick way to put one of your favorites on a speaker.** A 640×172 touch bar
that shows what is playing and lets you pick something else in one tap. That is
the whole product, and the constraints below follow from taking it literally:

- **Favorites are the content.** Not the library, not a search, not a curated
  list maintained in a config file. What you have marked favorite in Music
  Assistant is what the panel offers.
- **Prev and next move between favorites, not between tracks.** The bar is a
  station selector, not a transport for the current album. §2 covers what that
  leaves for the other buttons.
- **One configured playback device**, chosen by the user, changeable at
  runtime. The panel never addresses a speaker directly, so anything Music
  Assistant can drive works unchanged.
- **A playlist resumes where you left it.** Starting a playlist favorite a
  second time continues after the last track you heard rather than restarting.
  §5 covers where that state lives, and why it is not free.

Two hard dependencies, and the project is deliberately not abstracted away from
either:

**The panel.** One device today: the Waveshare ESP32-S3-Touch-LCD-3.49. The
AXS15231B drives display and touch from one chip over QSPI; the pin map, the
QSPI init sequence and the 172×640 native geometry are all board-specific. The
QMI8658 IMU sits on a *second* I²C bus at GPIO47/48, which is why an I²C scan of
the touch bus never finds it. 16MB flash, octal PSRAM at 80MHz — the framebuffer
needs it.

Everything board-specific is confined to `esphome/devices/waveshare-3.49.yaml`:
pins, geometry, and the tile size that follows from the layout. A second device
is a second profile, not a refactor. That is as far as the generalisation goes
on purpose — there is no runtime geometry negotiation and no per-device
branching, because one real device with fixed sizes is worth more than an
abstraction validated against nothing. Issues asking for a device, and pull
requests adding one, are both welcome.

**Music Assistant.** The panel uses MA's library API for the favorites list,
MA's image proxy for artwork, and `play_media` for playback.

Both dependencies track current releases. The project does not carry
compatibility shims for older ESPHome or Music Assistant versions; where a
recent version does something usefully better, the floor moves.

Everything the panel displays arrives at runtime. Changing your favorites, or
what the browser shows, never requires a rebuild or a reflash — see
[§7](#7-runtime-architecture). This is the central design goal and it
constrains most of what follows.

Three layers make that work: the ESPHome config on the device, Home Assistant
blueprints that resolve items and push pages, and an artwork normalizer that
guarantees every image arrives at identical dimensions. Only the first two are
required — [§4](#4-artwork) explains what the third buys and when its
constraint applies.

## 2. Screen layout

The bar is short and wide, which drives the whole UI. Two kinds of page:

**Now Playing** — a square artwork tile on the left, three text lines beside it
(album or station / artist / track, each scrolling when too long), a row of
icon transport buttons, and a full-height strip down the right edge that opens
the browser.

### What the transport buttons do

Prev and next move between **favorites**, not between tracks. That is the
deliberate part, and it is what makes the bar a station selector rather than a
second remote control for whatever is already playing — reaching the next
favorite is one tap, not a trip through the browser.

| Button | Action |
|---|---|
| Prev / Next | The previous or next favorite in the list, started immediately |
| Play / Pause | Pause and resume the configured player |
| Browser strip | Opens the browser |

Consequences worth stating rather than discovering:

- The panel is never the way to skip a track inside an album or playlist. That
  is what the phone or the speaker's own controls are for, and trying to serve
  both from four icons on a 172px-tall bar serves neither.
- Prev/next need a position in the favorites list. The device does not maintain
  one — it asks Home Assistant to move, and Home Assistant works out from what
  is playing where "next" lands. Keeping that in one place avoids the panel and
  Home Assistant disagreeing after playback is started from somewhere else.
- Playing something from the browser sets that position too, so next after a
  browser pick continues from the pick rather than from wherever the panel had
  got to.

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

Upstream agrees, and for a sharper reason than the one above. MA's library
database **keys radio stations off the stream URL**, so correcting a URL is not
an edit — it is a delete and re-add, and the `library://radio/N` changes.
Broadcasters rotate stream URLs routinely (the BBC is the running example in
[discussion #3279](https://github.com/orgs/music-assistant/discussions/3279)),
which makes this a normal maintenance action rather than a rare event. Asked
what a user should key automations on, the maintainer's answer is that they
should not have used the library URI at all. So the ID churn §3 is built around
is caused by ordinary use, not only by library rebuilds.

**Proven**: MA's `music/search` command resolves `"WKCR"` → `library://radio/17`.
Home Assistant exposes the same thing as `music_assistant.search`, a response
service taking `name` and `media_type`.

Two details about that search, both **proven** against the live instance and
both easy to get wrong:

- **Search results are keyed plural, except radio.** `music/search` returns
  `artists`, `albums`, `genres`, `tracks`, `playlists`, `radio`, `audiobooks`,
  `podcasts`, `sound_effects`. Reading the singular `media_type` back out of the
  response finds nothing for every type but radio, silently.
- **`library_only: true` is what returns library URIs.** Without it MA also
  searches every streaming provider and a provider hit can outrank the library
  item — `"Kind of Blue"` comes back as `spotify--…://album/…` rather than
  `library://album/N`. The normalizer searches the library first and only
  widens if that finds nothing, so a `list` section can still name something
  not yet in the library.

Three consequences to handle:

- Names must be unique within a media type. A config entry may carry an
  explicit `uri:` that overrides lookup, as the tiebreak for a genuine clash.
- A name that resolves to nothing renders as a tile marked unresolved rather
  than vanishing. A silently missing tile is a gap the user has to notice.
- Slugs, unlike names, share one namespace across media types, because a slug
  is a filename. A station and an album both called "Blue" collide; the second
  gets a suffixed filename and the run says so, rather than one tile silently
  disappearing.

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

### When this constraint applies at all

Only when artwork is configured. The panel draws its own monogram for any tile
it has no URL for, as an LVGL label on a coloured object — no image slot, no
buffer, no fetch. An install with no artwork configured hands its five browser
slots nothing, so there is nothing to reallocate and none of the above is
reachable.

That makes artwork an upgrade rather than a prerequisite, and it means the
browser can be built and proven before an image slot is ever used. The colour is
a hash of the item name, computed identically on both sides
(`esphome/includes/music_bar_monogram.h` and `fnv1a()` in the normalizer) so a tile
the panel draws and a tile the normalizer renders look the same; a test compiles
the header and diffs it against the Python.

The Now Playing thumbnail is a different risk from the five browser slots: one
buffer changing at track-change rate rather than five turning over on every page
turn. The prior build ran live Music Assistant artwork there and survived, which
is why tier 2 in the README offers it without a normalizer — but that is
inference from a build that also had far fewer slots, and it is folded into the
phase-1 probe rather than assumed.

### The contract, and what it is not

The interface between the panel and the artwork layer is *a folder of N×N PNGs
named by slug*. The normalizer is one way to fill that folder; a user dropping
84×84 squares into `/config/www/music-bar/` by hand is another, and needs no
software at all.

Nothing in the normalizer is specific to this panel beyond `tile_px` and
`mat_color` — "any image URL, returned at exactly N×N, flattened" is a
constraint every ESPHome device with runtime images has. It ships here as an
optional Home Assistant integration and a standalone script, and could
reasonably be extracted.

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

### Keeping it current without anyone thinking about it

Pages are built live from MA while artwork is pre-rendered, so the two can
disagree. Three obligations fall on the Home Assistant side to close that:

- **Trigger a run on an unknown slug.** A newly favorited item reaches a page
  immediately and has no image yet. When a page contains a slug absent from
  `manifest.json`, the integration runs the normalizer and the tile fills in on
  the next turn. Until it does, that tile is a monogram rather than a gap.
- **Re-probe gaps on a schedule.** The normalizer never caches "no artwork" —
  every run refetches for any item without an override — so a station that
  gains a logo upstream heals itself. Nothing else discovers that.
- **Refuse mismatched artwork.** The manifest records the `tile_px` it rendered
  at, and the panel publishes the size its image slots were built for as a
  diagnostic sensor. If those disagree, every image is the wrong shape and the
  reallocation problem returns; the integration pushes names only, with a
  notification, rather than destabilising the panel.

It also needs a **Refresh artwork** button, since that is the affordance the
gallery page tells users to press.

### What MA's own image editing does and does not cover

MA 2.9.0 added editing of the name and image of **manually added** stations,
tracks and playlists ([discussion #3279](https://github.com/orgs/music-assistant/discussions/3279)).
It does not make the override folder redundant, and it is worth being precise
about why.

**Proven** against the reference instance running 2.10.0b12: all 15 radios come
from `radiobrowser`, so the number the feature can fix there is **zero** — and
the five with no artwork are exactly the ones it cannot touch. Provider-sourced
items are not editable; only stations a user added by stream URL are. The two
mechanisms therefore cover different populations rather than competing:
MA-side images for manually added stations, overrides for everything from a
provider.

Where it does apply it composes cleanly. **Proven** on the reference instance,
after adding four stations manually with image URLs: each gets a `thumb` with
`provider: builtin`, `remotely_accessible: true`, the supplied URL as `path`,
**and a `proxy_id`**. All four fetch 200 through `?size=256&fmt=png`. So a user
who sets an image in MA needs no override at all — the normalizer picks it up
like any other artwork, and four stations that had been showing monograms
(WKCR, France Musique, Radio 3FACH, Rádio Amália) filled in on the next run.

It does not, however, remove the reason for normalizing — and the same
experiment shows why. Those four images came back at:

| Station | Size from MA's proxy |
|---|---|
| France Musique | 256×256 |
| Rádio Amália | 256×144 |
| WKCR | 256×138 |
| Radio 3FACH | 164×72 |

Four hand-curated images, four different buffer shapes, because the proxy
preserves aspect ratio and never upscales — Radio 3FACH's logo is small at
source, so `size=256` returns 164×72. Fixing artwork in MA fixes *coverage*, not
*dimensions*, and it is dimensions that the device's image slots care about. The
normalizer flattened all sixteen tiles to one `(84, 84)`.

A second thing that run showed: TSF Jazz has an artwork `path` and still came
back on a monogram, because the proxy did not return an image for it. Only a
real fetch settles whether artwork exists — which is exactly why that test lives
here and not on the device.

### Renames, and why the key stays the name

Renaming an item in MA changes its slug and orphans its override. This is the
one accepted limitation, and 2.9.0 made it more likely by turning renaming into
a supported operation users are invited to perform.

It stays accepted, because the same discussion establishes there is no stabler
key on offer: library URIs move whenever a stream URL is corrected, and the
provider IDs beneath them change upstream. Keying overrides on a URI would
trade a visible, self-announcing failure for a silent one.

What changed instead is the healing. The normalizer already reported override
files matching no item; it now pairs them against items that have fallen back
to a monogram and prints the `mv` that repairs it. Near-misses only — an orphan
resembling nothing is listed rather than guessed at, because a confident wrong
suggestion is worse than none.

### No artwork is redistributed

The repo ships none. `overrides/` is gitignored apart from its README, so a
fork cannot publish logos by accident, and the normalizer's output directory is
outside the repo. Artwork is fetched by the user, from their own MA instance,
onto their own machine. Monograms are generated from the item name, and the
only third-party asset in the build is the Material Design Icons webfont,
pulled at compile time rather than vendored.

Two placements, both viable:

**Pre-rendered (recommended).** A script normalizes every item in the
configured sections into a directory Home Assistant already serves —
`<ha-config>/www/music-bar/` at `http://<ha>:8123/local/music-bar/`. It reruns on a
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

**Favorites are the whole content model.** Across the media types the user
cares about, concatenated into one list that the browser pages through and that
prev/next steps along. There is no `all`, no capped library dump, and no
curated list maintained in a config file.

That is a narrowing from an earlier design, and it is worth being clear that it
has a cost. Favorites are only as useful as the user's tagging, and on the
reference instance the tagging is thin — **measured**, not estimated:

| Type | In library | Marked favorite |
|---|---|---|
| Radios | 16 | **0** |
| Playlists | 101 | 5 |
| Albums | 419 | 0 |
| Artists | 469 | 0 |
| Tracks | 2000+ | 0 |

So the panel on the reference install would today show **five playlists and no
radio at all**, including none of the four stations that were hand-curated with
logos. Radio is the media type this hardware is most obviously for, and it is
the one with zero favorites — which is a fair summary of the risk this decision
carries. The response
is not to add fallbacks to the panel — it is that **favoriting is the interface**.
Marking something favorite in any Music Assistant client is how it reaches the
bar, and it takes one tap in an app the user already has. A config file listing
station names would be a second, worse copy of a thing MA already stores, and
[§3](#3-items-are-chosen-by-name) exists because that copy drifts.

The first-run consequence is real and needs handling rather than hiding: a user
with nothing favorited gets an empty browser. The panel says so, and says what
to do about it, instead of showing five blank tiles.

### Resuming a playlist

Starting a playlist favorite continues after the last track heard, rather than
restarting it. Both halves of this cost something.

**Where to start from.** MA supports it natively — **proven** in
`player_queues.play_media`, which takes `start_item: "Optional item to start the
playlist or album from"`. But **proven** the other way too: Home Assistant's
`music_assistant` integration does not expose it. Its whole service surface is
`play_media`, `play_announcement`, `transfer_queue`, `search`, `get_queue` and
`get_library`, and `play_media` takes only `media_id`, `media_type`, `artist`,
`album`, `enqueue` and `radio_mode`.

Two ways through, both requiring MA's own API rather than Home Assistant's:

- Call `player_queues/play_media` directly with `start_item`.
- Or read `music/playlists/playlist_tracks` — **proven** to return each track
  with its `position` and `uri` — and pass the URIs from the resume point
  onward as `media_id`, which MA accepts as a list.

**Where the position is remembered.** Not in MA. Its `resume_pos` is elapsed
seconds within the *current* queue, not a memory of where you were in a given
playlist last week. So this project stores it: playlist URI → last played track,
updated as playback moves.

The consequence for the install tiers is the honest part. Everything else the
panel does works with blueprints alone, but resume needs a Music Assistant
token — the same credential the artwork layer already uses. So resume belongs
with the artwork integration rather than with the blueprints, and a
blueprints-only install starts playlists from the top. That is a working panel,
not a broken one.

## 6. The Home Assistant contract

Home Assistant holds all the logic. The device holds none of it, which is what
lets the browser change without a rebuild.

**Now playing** reaches the device as flat sensors — title, artist,
album-or-station, playback state, artwork URL — rather than as a media player
entity, because the useful fields are scattered across MA's entity model and
template logic belongs in Home Assistant, not in device YAML. This repo ships
those templates as an importable blueprint, so setting one up is picking a
player from a dropdown rather than editing YAML.

**Choosing the player** happens in Home Assistant, not on the panel. The
blueprint takes the Music Assistant player as its target, so changing speakers
is changing one field — and the panel keeps knowing nothing about speakers,
which is what lets any player MA supports work.

It is worth recording why the obvious alternative is not available: an ESPHome
`select` has a **compile-time** options list, so a "pick your speaker" dropdown
on the device cannot be populated from Home Assistant at runtime. A panel-side
affordance is therefore a *cycle* — a button asking Home Assistant to move to
the next player it knows about — rather than a list. That is a later addition;
the blueprint field is the mechanism.

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

- **ESPHome 2026.7.3 or newer**, which is what this is developed and tested
  against. The floor tracks current releases rather than reaching back: the
  project carries no compatibility shims, and 2026.5 was already required
  because the panel uses a global `lvgl: rotation: 90°` with the display and
  touchscreen left native, and only current ESPHome rotates LVGL hit-testing to
  match. The raw `touchscreen: on_touch` trigger still reports un-rotated
  coordinates, which is expected rather than a bug.
- **Music Assistant 2.10 or newer**, the version this is developed against.
  Older releases are not worked around.
- **Home Assistant's per-device action toggle must be on.** Settings → Devices
  & Services → ESPHome → *device* → gear → "Allow the device to perform Home
  Assistant actions". It defaults off on recent Home Assistant and silently
  no-ops every service call with no error logged anywhere: buttons visibly
  react and nothing happens. The panel detects this for itself — it calls
  `script.music_bar_hello` on connect and expects a call back to its `hello_ack`
  action, and says what is wrong on screen when none arrives. See
  [adoption.md](adoption.md#the-handshake-and-the-toggle-it-exists-for).
- **A Music Assistant long-lived token**, created in the MA UI under Settings →
  Profile. The token embedded in Home Assistant's `music_assistant` config
  entry is a different credential and does not authenticate against MA's own
  API port. This is the project's only credential, and it belongs to the
  artwork layer — the panel itself needs none.
- **Somewhere to run the normalizer**, with Pillow. Any host that can reach MA
  and write to Home Assistant's `www` folder. Only needed if you want artwork;
  without it the panel draws monograms.
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
- **How is "the next favorite" derived from what is playing?** Prev/next step
  along the favorites list, so Home Assistant has to map the currently playing
  item back to a position in it. Exact URI match is the obvious route and is
  **unverified** for the case where playback was started elsewhere, or where a
  playlist favorite is playing so the current item is a *track* rather than the
  playlist. *Probe*: start a playlist favorite, read `get_queue`, and check
  whether anything in it identifies the playlist it came from. If nothing does,
  the position is state this project keeps rather than something it can infer.
- **Does resume need MA's API, or will `media_id` as a list do?** MA accepts a
  list of URIs, so passing tracks from the resume point may avoid needing
  `start_item`. Both routes still need `playlist_tracks`, which Home Assistant
  does not expose — so **unverified** is whether any blueprints-only resume is
  possible at all. *Probe*: call `music_assistant.play_media` with a list of
  track URIs and confirm the queue matches.
- ~~**Is an image set in MA's own editor served through the proxy?**~~
  **Answered**: yes, with a `proxy_id`, fetchable at `?size=256&fmt=png`. It
  also comes back at the source's aspect ratio rather than square, so it needs
  normalizing like anything else. See [§4](#what-mas-own-image-editing-does-and-does-not-cover).
