#!/usr/bin/env python3
"""
Generate the hifi-panel radio-station pages from the Music Assistant library.

The station list used to be hardcoded in *three* places — the ESPHome config,
the `input_select.radio_station` options, and a name->URI map inside the
`radio_play_selected_station` HA automation. This script replaces all of that:
it reads the library from Music Assistant and emits ESPHome YAML that plays
each station by its stable `library://radio/N` URI, so nothing has to agree on
display names.

What it emits, spliced into hifi-panel.yaml between marker comments:

  1. `image:` entries for every station whose artwork actually resolves.
     These use ESPHome's build-time web fetch, so the logos are compiled into
     flash: no runtime download, no decode, no PSRAM buffer. See
     docs/hifi-panel.md for why that matters on this device.
  2. LVGL pages of station tiles — logo where one exists, a radio icon where
     it doesn't.

Artwork comes from Music Assistant's image proxy with `?size=&fmt=png`, which
bounds it server-side. Do not point this at the raw `path` from the API: those
are origin URLs of arbitrary size and format, and some are already dead.

Usage:
    scripts/esphome/gen-radio-stations.py [--config PATH] [--dry-run]

Requires `MA_API_TOKEN` in secrets.yaml (create one in the Music Assistant UI
under Settings -> Profile).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "secrets.yaml"

MA_URL = "http://192.168.1.171:8095"
DEFAULT_CONFIG = Path("/tmp/esphome-build/hifi-panel.yaml")

# The media_player Music Assistant plays through (its own queue entity, not the
# WiiM entity — see docs/hifi-panel.md).
MA_PLAYER = "media_player.living_room_3"

# Ask MA for this; it only allows 80/160/256/512 and never upscales.
PROXY_SIZE = 256
# Compile the logo into flash at this size. Fits the tile below with margin.
# 84px needs ?size=256 from MA (the allowed steps are 80/160/256/512 and it
# never upscales, so asking for 160 would cap the source below the tile).
LOGO_PX = 84

# ── Tile geometry, for a 640x172 landscape panel ────────────────────────────
# 5 across rather than 6: bigger artwork, and enough width under it for a
# station name to wrap to two readable lines.
PAGE_W, PAGE_H = 640, 172
NAV_W = 46           # left/right paging buttons
TILES_PER_PAGE = 5
TILE_X0 = 50
TILE_PITCH = 109
TILE_W, TILE_H = 104, 164
TILE_Y = 4

MARKERS = {
    "logos": ("# >>> BEGIN GENERATED STATION LOGOS", "# <<< END GENERATED STATION LOGOS"),
    "pages": ("# >>> BEGIN GENERATED RADIO PAGES", "# <<< END GENERATED RADIO PAGES"),
}

ICON_RADIO = r"\U000F0439"
ICON_CHEV_L = r"\U000F0141"
ICON_CHEV_R = r"\U000F0142"


def read_secret(key: str) -> str:
    for line in SECRETS.read_text().splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    sys.exit(f"error: {key} not found in {SECRETS}")


def ma_command(token: str, command: str, args: dict | None = None):
    body = json.dumps({"message_id": "1", "command": command, "args": args or {}}).encode()
    req = urllib.request.Request(
        f"{MA_URL}/api",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def logo_url(proxy_id: str) -> str:
    return f"{MA_URL}/imageproxy/{proxy_id}?size={PROXY_SIZE}&fmt=png"


def resolves(url: str) -> bool:
    """A proxy_id is returned even when MA has no artwork, and the proxy 404s
    for those — so `proxy_id is not None` is NOT a usable 'has artwork' test.
    Only a real fetch tells you."""
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status == 200 and len(r.read()) > 0
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"logo_{s}"[:40]


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_logos(stations: list[dict]) -> str:
    out = []
    for st in stations:
        if not st["logo"]:
            continue
        out += [
            f"  - platform: file",
            f"    id: {st['slug']}",
            # Shorthand form on purpose: the documented mapping form
            # (file: {source: web, url: ...}) crashes ESPHome 2026.7.3 with
            # "TypeError: 'str' object does not support item assignment".
            f"    file: {yaml_str(st['logo'])}",
            f"    type: RGB565",
            f"    resize: {LOGO_PX}x{LOGO_PX}",
            # Station logos are frequently transparent PNGs; without this the
            # undefined RGB under transparent pixels gets painted.
            f"    transparency: ALPHA_CHANNEL",
        ]
    return "\n".join(out)


def build_tile(st: dict, x: int) -> list[str]:
    """One station tile: artwork (or a radio glyph) on a grey mat, name below."""
    art = (
        [
            f"                    - image:",
            f"                        src: {st['slug']}",
            f"                        align: CENTER",
        ]
        if st["logo"]
        else [
            f"                    - label:",
            f'                        text: "{ICON_RADIO}"',
            f"                        align: CENTER",
            f"                        text_font: font_icon",
            f"                        text_color: 0x404040",
        ]
    )
    return [
        f"        - button:",
        f"            x: {x}",
        f"            y: {TILE_Y}",
        f"            width: {TILE_W}",
        f"            height: {TILE_H}",
        # Override the blue theme: a grid of blue tiles fights the artwork.
        f"            bg_color: 0x1E1E1E",
        f"            radius: 8",
        f"            on_press:",
        # Play by URI. Names are display strings and drift; library://radio/N
        # is stable, which is what lets this file be regenerated safely.
        f"              - homeassistant.action:",
        f"                  action: music_assistant.play_media",
        f"                  data:",
        f"                    entity_id: {MA_PLAYER}",
        f"                    media_id: {yaml_str(st['uri'])}",
        f"                    media_type: radio",
        f"              - lvgl.page.show: page_now_playing",
        f"            widgets:",
        f"              - obj:",
        f"                  align: TOP_MID",
        f"                  y: 6",
        f"                  width: {LOGO_PX + 4}",
        f"                  height: {LOGO_PX + 4}",
        # Mid-grey mat: transparent logos come in both polarities, so neither
        # black nor white keeps all of them legible.
        f"                  bg_color: 0x808080",
        f"                  bg_opa: COVER",
        f"                  radius: 6",
        f"                  border_width: 0",
        f"                  pad_all: 0",
        f"                  scrollable: false",
        # A plain lv_obj is CLICKABLE by default (lv_obj.c: obj->flags =
        # LV_OBJ_FLAG_CLICKABLE), so this mat swallowed taps over the artwork
        # and only the station-name label — labels and images both REMOVE the
        # flag — let presses reach the button underneath.
        f"                  clickable: false",
        f"                  widgets:",
        *art,
        f"              - label:",
        f"                  align: TOP_MID",
        f"                  y: {LOGO_PX + 14}",
        f"                  width: {TILE_W - 6}",
        f"                  text: {yaml_str(st['name'])}",
        f"                  text_font: font_sm",
        f"                  text_color: 0xFFFFFF",
        f"                  long_mode: WRAP",
        f"                  text_align: CENTER",
    ]


def build_pages(stations: list[dict]) -> str:
    pages = [stations[i : i + TILES_PER_PAGE] for i in range(0, len(stations), TILES_PER_PAGE)]
    out = []
    for n, group in enumerate(pages, 1):
        out += [
            f"    # ── Radio {n}/{len(pages)} " + "─" * 40,
            f"    - id: page_radio_{n}",
            f"      bg_color: 0x000000",
            f"      scrollable: false",
            f"      scrollbar_mode: 'OFF'",
            f"      widgets:",
            f"        - button:",
            f"            x: 0",
            f"            y: 0",
            f"            width: {NAV_W}",
            f"            height: {PAGE_H}",
            f"            radius: 0",
            f"            on_press:",
            f"              - lvgl.page.previous:",
            f"            widgets:",
            f'              - label: {{ align: CENTER, text: "{ICON_CHEV_L}", text_font: font_icon }}',
            f"        - button:",
            f"            x: {PAGE_W - NAV_W}",
            f"            y: 0",
            f"            width: {NAV_W}",
            f"            height: {PAGE_H}",
            f"            radius: 0",
            f"            on_press:",
            f"              - lvgl.page.next:",
            f"            widgets:",
            f'              - label: {{ align: CENTER, text: "{ICON_CHEV_R}", text_font: font_icon }}',
        ]
        for i, st in enumerate(group):
            out += build_tile(st, TILE_X0 + i * TILE_PITCH)
    return "\n".join(out)


def splice(text: str, key: str, body: str) -> str:
    begin, end = MARKERS[key]
    pat = re.compile(
        rf"([ \t]*){re.escape(begin)}.*?{re.escape(end)}", re.DOTALL
    )
    if not pat.search(text):
        sys.exit(f"error: markers for '{key}' not found in config.\n"
                 f"       Add these two lines where the block should go:\n"
                 f"         {begin}\n         {end}")
    def repl(m):
        indent = m.group(1)
        return f"{indent}{begin}\n{body}\n{indent}{end}"
    return pat.sub(repl, text, count=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                    help=f"hifi-panel.yaml to rewrite (default: {DEFAULT_CONFIG})")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the generated YAML instead of writing")
    args = ap.parse_args()

    token = read_secret("MA_API_TOKEN")
    print(f"querying {MA_URL} …")
    items = ma_command(token, "music/radios/library_items", {"limit": 100})
    if not isinstance(items, list):
        sys.exit(f"unexpected API response: {str(items)[:200]}")

    stations = []
    for it in sorted(items, key=lambda x: x["name"].lower()):
        imgs = (it.get("metadata") or {}).get("images") or []
        pid = imgs[0].get("proxy_id") if imgs else None
        url = logo_url(pid) if pid else None
        have = bool(url) and resolves(url)
        stations.append({
            "name": it["name"],
            "uri": it["uri"],
            "slug": slug(it["name"]),
            "logo": url if have else None,
            "raw": (imgs[0].get("path") if imgs else "") or "",
        })
        mark = "logo" if have else ("dead origin" if (imgs and imgs[0].get("path")) else "no artwork")
        print(f"  {it['name'][:38]:40s} {it['uri']:22s} {mark}")

    n_logo = sum(1 for s in stations if s["logo"])
    flash = n_logo * LOGO_PX * LOGO_PX * 3
    print(f"\n{len(stations)} stations, {n_logo} with artwork "
          f"(~{flash/1024:.0f} KB of flash at {LOGO_PX}x{LOGO_PX} RGB565A8)")
    missing = [s["name"] for s in stations if not s["logo"]]
    if missing:
        print("no artwork (tiles fall back to a radio icon):")
        for m in missing:
            print(f"  - {m}")

    logos, pages = build_logos(stations), build_pages(stations)
    if args.dry_run:
        print("\n" + "=" * 70 + "\n" + logos + "\n\n" + pages)
        return 0

    cfg = args.config
    if not cfg.is_file():
        sys.exit(f"error: {cfg} not found (pass --config)")
    text = cfg.read_text()
    text = splice(text, "logos", logos)
    text = splice(text, "pages", pages)
    cfg.write_text(text)
    print(f"\nwrote {cfg}")
    print("next: esphome run hifi-panel.yaml --device 192.168.1.87 --no-logs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
