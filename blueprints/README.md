# Blueprints

The Home Assistant half of the panel. Two automations: one sends what's playing
to the panel, the other answers everything the panel asks for.

They ship as blueprints rather than as a package file so there is nothing to
place on disk, nothing to edit, and no restart — you import them and pick your
player from a dropdown.

## Installing

Settings → Automations & Scenes → Blueprints → **Import Blueprint**, and paste
the URL of each file. Then create an automation from each.

| Blueprint | What it does |
|---|---|
| `now_playing.yaml` | Watches a Music Assistant player and pushes title, artist, album and artwork to the panel |
| `favorites.yaml` | Answers the panel's handshake, serves pages of your favorites, and plays what you tap or skip to |

Create **both**. They send in opposite directions and neither is much use
alone: without Now Playing the screen stays blank, and without Favorites the
buttons do nothing and the panel reports that Home Assistant never answered.

## One automation each

Create **exactly one** automation from each blueprint, per panel.

Every automation created from a blueprint fires on the same triggers. Two Now
Playing automations both push text to the same panel, a moment apart; if they
are configured with different players, the panel shows whichever replied last
and looks like it is displaying stale or random information. Two Favorites
automations answer every request twice.

This is easy to do by accident, because saving a blueprint configuration again
after changing a field creates a *new* automation rather than editing the old
one unless you reopen the existing automation to edit it.

To check: Settings → Automations, filter by blueprint. The blueprint page also
shows how many automations use it — anything above one per panel is a duplicate.

## Which player to follow

The Favorites automation must use a **Music Assistant** player: it reads your
favorites and starts playback through Music Assistant, and its library call is
resolved from that entity's integration.

Now Playing can follow either:

- the **same Music Assistant player** — normal, and what the panel's own tiles
  drive; or
- the **speaker's own entity** — if you want the panel to show everything the
  speaker plays, including Bluetooth, line-in or Spotify Connect, which Music
  Assistant knows nothing about.

A speaker usually appears twice in Home Assistant, once per integration. If the
panel shows nothing while music is definitely playing, it is usually because
playback was started on one of those entities and the panel is watching the
other.

## What you need to know

**The panel's device name.** Now Playing asks for it, because it is triggered by
your player rather than by the panel and so has nothing to read it from. It is
the ESPHome hostname, not the friendly name — `music-bar-a1b2c3` rather than
`Kitchen Panel`, because the firmware appends the MAC so that several unflashed
panels do not collide on first boot. Settings → Devices & Services → ESPHome
shows it.

Favorites does not ask: the panel puts its own name in every event it fires.

**Favoriting is how things get on the panel.** There is no list to maintain
here. Mark something favorite in any Music Assistant client and it appears on
the next page turn. If the panel shows nothing, that is usually the answer —
check what you actually have favorited, not the automation.

**Prev and next move between favorites, not tracks.** The panel is a station
selector. Skipping inside an album or playlist is what your phone is for.

## The one setting that catches everyone

Home Assistant's per-device **"Allow the device to perform Home Assistant
actions"** toggle defaults *off*, and silently drops every event the panel
fires — nothing is logged anywhere. The panel detects this itself and says so
on screen and in its **Setup Status** entity, but it cannot fix it.

Settings → Devices & Services → ESPHome → your panel → gear icon → enable it.
Then press the panel's **Retry Home Assistant Handshake** button; no reboot
needed.

## Testing without a screen

The firmware exposes its controls as entities, so the whole contract can be
exercised from the panel's Home Assistant device page before the display exists:

- **Previous / Next Favorite**, **Play Pause** — the transport
- **Next / Previous Page** — paging
- **Tile Number** + **Play Selected Tile** — stands in for tapping a tile

Watch **Setup Status** to see whether the handshake landed.

## Artwork

These blueprints send no artwork URLs for browser tiles, so tiles show the
panel's own monograms — the item's initials on a colour derived from its name.
That is the intended tier-2 experience, not a missing feature: with no URLs
handed out, the panel never allocates an image buffer, which is what keeps it
away from the PSRAM fragmentation described in [`../docs/spec.md`](../docs/spec.md)
§4.

Now Playing artwork *is* sent, from the player's own `entity_picture` — one
image changing at track-change rate rather than five per page turn.

Install the artwork integration to replace tile monograms with real images.
