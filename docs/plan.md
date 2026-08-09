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

Built and tested against a live 20-item library:

- **The spec.** Every claim marked *proven* was measured on hardware, probed
  against a running Music Assistant, or read out of the ESPHome source.
- **The artwork normalizer** (`scripts/normalize-artwork.py`) — resolves items,
  fetches and squares artwork, generates monograms for gaps, fingerprints each
  tile, and writes the onboarding gallery.

Not built: the ESPHome config, and the Home Assistant package.

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

### 1. Measure the runtime image slots

The riskiest unknown, and cheap to answer now: the normalizer's output is
already static files at fixed URLs, so this needs no Home Assistant package and
no browser logic. A throwaway config with six slots and a button that cycles
their URLs is enough.

Answers three of the open questions in [spec §10](spec.md#10-open-questions),
and everything after it assumes the answers.

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

### 3. The browser

The new part. Five tile widgets, a Home Assistant script that pages
`get_library`, and the API action carrying names, URLs and URIs back — see
[spec §6](spec.md#6-the-home-assistant-contract) and
[§7](spec.md#7-runtime-architecture).

*Done when*: favoriting a playlist in Music Assistant puts it on the panel with
correct artwork, without a rebuild.

### 4. Guards and self-healing

The three obligations in [spec §4](spec.md#4-artwork) that keep it accurate
without anyone thinking about it: trigger a normalizer run on an unknown slug,
re-probe gaps on a schedule, and refuse artwork whose `tile_px` disagrees with
the firmware. Plus the **Refresh artwork** button the gallery page points at.

*Done when*: each row of the README's "what happens when things change" table
has been performed against the real system and behaved as written.

### 5. Release

Install instructions, an example Home Assistant package, photographs of the
thing on a shelf. Also the IMU auto-rotation, which was implemented in the
prior build but never actually observed rotating the screen — it either works
or it comes out.

*Done when*: someone else's install works from the README alone.

## Settled decisions

Recorded so they are not reopened without new information.

| Decision | Because |
|---|---|
| Items addressed by name, not URI | MA's `library://type/N` are row IDs local to one install; the radio-browser IDs beneath them change upstream. Names survive both. |
| Live pages, not build-time generation | Changing favorites should not mean reflashing. Everything else follows from this. |
| Artwork through a normalizer | ESPHome reallocates an image buffer whenever decoded dimensions change, and `resize:` preserves aspect ratio rather than squaring. Uniform dimensions are what make live mode safe. |
| Monogram for gaps, not a shared icon | A page of identical placeholders reads as breakage; initials on a name-derived colour reads as design. |
| Rounded corners, no inset | Most logos are opaque with their own background. Rounding unifies them; insetting shrinks the logo's background too and puts a sharp square inside the rounded card. |
| No artwork in the repo | Logos and covers are someone else's copyright. Users fetch their own. |
| MIT | Matches the rest of the author's ESPHome work. |
