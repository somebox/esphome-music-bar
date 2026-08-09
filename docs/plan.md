# Context and plan

Where this project came from, what is built, and what happens next.
[`spec.md`](spec.md) holds the design itself; this file holds the reasoning
around it and the order of work.

## Where it came from

In August 2026 a single 63KB ESPHome config called `hifi-panel` was built for
one Waveshare ESP32-S3-Touch-LCD-3.49 sitting next to a WiiM streamer. It
worked, and getting it to work turned up a lot that is not written down
anywhere: how the AXS15231B behaves, how LVGL rotation interacts with touch,
what Music Assistant's image proxy actually returns, and several ways an image
can decode perfectly and still render wrong.

Almost none of that was about the WiiM. The speaker was incidental — the panel
never talks to it, only to Music Assistant. What the work was really tied to
was the board and the backend, which is what the name says and what the scope
in [spec §1](spec.md#1-scope) fixes.

The original also generated its browser pages at build time and compiled
station logos into flash. That was a sound answer to a real constraint, but it
means changing your favorites requires regenerating and reflashing. Removing
that is the reason this is a rewrite rather than a copy.

## Status

Built:

- **The spec.** Every claim marked *proven* was measured on hardware, probed
  against a running Music Assistant, or read out of the ESPHome source.
- **The artwork normalizer** (`scripts/normalize-artwork.py`) — resolves items,
  fetches and squares artwork, generates monograms for gaps, fingerprints each
  tile, and writes the onboarding gallery. Tested against a live 20-item
  library, plus a unit suite covering its pure functions.
- **The ESPHome onboarding half** (`esphome/`) — provisioning over Improv, a
  runtime Noise key, `dashboard_import`, diagnostics, recovery buttons, the
  three API actions Home Assistant will call, and the setup-state handshake.
  Validates and compiles; **never flashed to hardware**.
- **Device-drawn monograms** (`esphome/includes/music_bar_monogram.h`) — the shared
  hash, with a test that compiles the header and diffs it against the Python.

Not built: the display and LVGL layout, the blueprints, and the artwork
integration for Home Assistant.

One measurement from the first compile, worth carrying into phase 1: the
factory image already uses **42.2% of internal RAM** (144KB of 342KB) with no
display in it. BLE provisioning is part of that and the LVGL draw buffers are
not yet.

## Where the layers sit

Artwork is an upgrade, not a prerequisite. The panel draws its own monograms, so
the browser works with nothing beyond the firmware and a blueprint — and with no
artwork configured, no image slot is handed a URL, so the fragmentation
constraint in [spec §4](spec.md#4-artwork) does not apply at all. It applies
exactly when artwork is configured, which is when the normalizer guarantees
fixed dimensions.

The contract with the artwork layer is *a folder of N×N PNGs named by slug*. The
normalizer is one way to fill it; a user dropping 84×84 squares in by hand is
another.

| Layer | Owns | Required |
|---|---|---|
| Firmware | Layout, tiles, image slots, the API contract | Yes |
| Blueprints | Resolving names, paging the library, pushing payloads | For anything to appear |
| Artwork | Any image URL → exactly N×N at a stable URL | No |

## Prerequisites

Independent of the phases below, and worth confirming before starting any of
them. Full detail in [spec §8](spec.md#8-prerequisites).

- ESPHome 2026.5+ (developed against 2026.7.3) — earlier versions rotate LVGL
  touch input incorrectly.
- Home Assistant with the Music Assistant integration, and the per-device
  "Allow the device to perform Home Assistant actions" toggle **on**. It
  defaults off and silently no-ops every service call.
- A Music Assistant long-lived token, from Settings → Profile. Not the one
  inside Home Assistant's config entry.
- Somewhere to run the normalizer, with Pillow.

## Phases

### 0. Retrieve `hifi-panel`

It is on the ESPHome host, not in this repo. Everything below needs it, and
reconstructing the AXS15231B QSPI init sequence from scratch is a bad trade
against fetching a file.

### 1. Bring up the display, then measure the runtime image slots

Originally planned as the first phase on the grounds that it needed nothing
else. It does: `online_image` is a display-domain component and ESPHome refuses
it without a `display:` block, so the probe cannot be built before the display
port. `esphome/probe-image-slots.yaml` is written and waiting for one.

Still the riskiest unknown, and everything after it assumes the answers. Answers
three of the open questions in [spec §10](spec.md#10-open-questions), plus the
BLE-versus-framebuffer question in [adoption.md](adoption.md#open-questions).

*Done when*: thirty forced page swaps leave the largest free PSRAM block
unmoved, and the interval from swap to fifth `on_download_finished` is
measured, cold and warm.

### 2. Now Playing

Port the proven half of `hifi-panel`: the layout, the transport controls, the
single now-playing thumbnail, and the flat Home Assistant sensors behind them.
No browser yet. This is the part that already works, carried across with its
comments intact.

*Done when*: the panel shows live track, artist and station text with correct
artwork, and the transport buttons drive a Music Assistant player.

### 3. Favorites: the browser and prev/next, on monograms alone

Five tile widgets, a blueprint that pages favorites with `get_library`, and the
`page` API action carrying names, URLs and URIs back — see
[spec §6](spec.md#6-the-home-assistant-contract) and
[§7](spec.md#7-runtime-architecture). The action already exists and copies its
arrays into globals; this phase writes the widgets and the blueprint.

Prev/next land here rather than with the transport in phase 2, because they
step along the favorites list and there is no list before this phase. That
brings its own open question — how Home Assistant maps what is playing back to
a position (see [spec §10](spec.md#10-open-questions)); settle it with the probe
before writing the automation around it.

Artwork stays off for the whole phase, so the browser is proven end to end
before an image slot is ever handed a URL. Tiles show the panel's own monograms,
using `music_bar::monogram_bg_hex()`.

Also here: the empty-favorites case. A user with nothing favorited should be
told to go favorite something, not shown five blank tiles.

*Done when*: favoriting a playlist in Music Assistant puts it on the panel
without a rebuild and with no artwork configured anywhere, and next moves to it.

### 4. Artwork and resume

Two things that both need a Music Assistant token, which is why they share a
phase and why both live in the integration rather than the blueprints.

Point the five slots at URLs. Then the Home Assistant integration
(`custom_components/music_bar_artwork/`) wrapping the normalizer: a config flow,
a **Refresh artwork** button, and the three obligations in
[spec §4](spec.md#4-artwork) — trigger a run on an unknown slug, re-probe gaps
on a schedule, and refuse artwork whose `tile_px` disagrees with the size the
panel reports.

Then playlist resume ([spec §5](spec.md#resuming-a-playlist)): record the last
track played per playlist, and start from the next one. Needs
`music/playlists/playlist_tracks` and either `start_item` or a track-URI list,
none of which Home Assistant exposes.

An integration rather than an add-on because it declares its own requirements
and so installs on Home Assistant OS, Supervised, Container and Core alike.

*Done when*: installing the integration fills in the same tiles that were
showing monograms, on the next page turn, with no reflash; a playlist started
twice does not restart the second time; and each row of the README's "what
happens when things change" table has been performed against the real system.

### 5. Release

Install instructions, a published web-flasher binary, photographs of the thing
on a shelf. Also the IMU auto-rotation, which was implemented in the
prior build but never actually observed rotating the screen — it either works
or it comes out.

*Done when*: someone else's install works from the README alone.

## Settled decisions

Recorded so they are not reopened without new information.

| Decision | Because |
|---|---|
| Favorites are the only content source | Favoriting is one tap in a client the user already has, and it is where MA already keeps this. A config file of station names would be a second copy that drifts. Costs: a user with no favorites gets an empty panel, which phase 3 has to say out loud. |
| Prev/next move between favorites, not tracks | Makes the bar a station selector rather than a second remote for whatever is playing. Four icons on a 172px bar cannot serve both. |
| One device profile, no runtime geometry | `devices/waveshare-3.49.yaml` holds pins, geometry and tile size; a second device is a second profile. An abstraction validated against one device is not an abstraction. |
| Track current ESPHome and MA, no shims | Both move fast and the useful features are recent. `start_item`, runtime Noise keys and correct LVGL touch rotation are all recent; supporting older releases would cost more than it buys. |
| Resume lives with the artwork integration | It needs `playlist_tracks` and `start_item`, neither of which Home Assistant exposes, so it needs an MA token — the same one the artwork layer already has. Blueprints-only installs start playlists from the top. |
| Items addressed by name, not URI | MA's `library://type/N` are row IDs local to one install; the radio-browser IDs beneath them change upstream. Names survive both. |
| Live pages, not build-time generation | Changing favorites should not mean reflashing. Everything else follows from this. |
| Artwork through a normalizer | ESPHome reallocates an image buffer whenever decoded dimensions change, and `resize:` preserves aspect ratio rather than squaring. Uniform dimensions are what make live mode safe. |
| Monogram for gaps, not a shared icon | A page of identical placeholders reads as breakage; initials on a name-derived colour reads as design. |
| Rounded corners, no inset | Most logos are opaque with their own background. Rounding unifies them; insetting shrinks the logo's background too and puts a sharp square inside the rounded card. |
| No artwork in the repo | Logos and covers are someone else's copyright. Users fetch their own. |
| MIT | Matches the rest of the author's ESPHome work. |
| No secrets in the firmware | Improv provisions Wi-Fi and Home Assistant hands over a Noise key at adoption. Everything else the panel shows arrives at runtime, so there is nothing left to configure — which is also what Made for ESPHome requires. |
| Monograms drawn on the device | Makes artwork optional rather than a prerequisite, and removes the fragmentation risk entirely from installs that have no artwork. |
| One hash, two implementations, one test | The panel and the normalizer must pick the same colour for an item. A test compiles the header and diffs it against the Python rather than trusting that they stay in step. |
| Artwork as an integration, not an add-on | An integration declares its own requirements, so it installs on every Home Assistant flavour. Add-ons only work on OS and Supervised. |
| Blueprints, not a package file | Import and pick a player from a dropdown; no file to place, no YAML to edit, no restart. |
| `import_full_config: false` | Adoption copies the config's text, which would break the `!include`. Referencing it as a remote package resolves the include from the clone. See [adoption.md](adoption.md#why-import_full_config-is-false). |
