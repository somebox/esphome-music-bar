#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.1", "pyyaml>=6"]
# ///
"""
Normalize artwork for every item the ma-bar browser can show.

Emits one PNG per item at exactly tile_px square, so the panel's image slots
allocate their buffers once and never reallocate. ESPHome frees and reallocates
a runtime image buffer whenever decoded dimensions change, and its `resize:`
preserves aspect ratio rather than forcing a square, so artwork of mixed shapes
fragments PSRAM across page turns. See docs/spec.md section 4.

Artwork for each item resolves in this order:

  1. your own file in overrides_dir, named after the item's slug
  2. Music Assistant's image proxy, if it actually returns an image
  3. a generated monogram, coloured from the item name

Nothing is ever left blank, and nothing unbounded reaches the device.

Usage:
    scripts/normalize-artwork.py --config ma-bar.config.yaml
    scripts/normalize-artwork.py --report          # what has what, write nothing
    scripts/normalize-artwork.py --out /tmp/try    # somewhere else, for a look
"""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent

# MA's own endpoint names are plural; the config's media_type is singular
# because that is what Home Assistant's services take.
ENDPOINT = {
    "radio": "radios",
    "playlist": "playlists",
    "album": "albums",
    "artist": "artists",
    "track": "tracks",
}

OVERRIDE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


# ── Music Assistant ─────────────────────────────────────────────────────────


class MusicAssistant:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token

    def command(self, command: str, args: dict | None = None):
        body = json.dumps(
            {"message_id": "1", "command": command, "args": args or {}}
        ).encode()
        req = urllib.request.Request(
            f"{self.url}/api",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def library(self, media_type: str, favorite: bool, limit: int) -> list[dict]:
        args: dict = {"limit": limit}
        if favorite:
            args["favorite"] = True
        return self.command(f"music/{ENDPOINT[media_type]}/library_items", args)

    def find(self, name: str, media_type: str) -> dict | None:
        """Resolve a name to a library item. Exact match wins; otherwise the
        first result, because MA orders by relevance."""
        res = self.command(
            "music/search",
            {"search_query": name, "media_types": [media_type], "limit": 5},
        )
        hits = res.get(media_type if media_type != "radio" else "radio", [])
        if not hits:
            return None
        for h in hits:
            if h.get("name", "").casefold() == name.casefold():
                return h
        return hits[0]

    def artwork_url(self, item: dict, size: int) -> str | None:
        """The proxy URL for an item's thumbnail, if it claims to have one.

        A proxy_id is returned even when there is no artwork and the proxy 404s
        for those, so this is a candidate rather than an answer — only fetching
        settles it.
        """
        images = (item.get("metadata") or {}).get("images") or []
        thumb = next((i for i in images if i.get("type") == "thumb"), None)
        thumb = thumb or (images[0] if images else None)
        if not thumb or not thumb.get("proxy_id"):
            return None
        return f"{self.url}/imageproxy/{thumb['proxy_id']}?size={size}&fmt=png"


def fetch(url: str, timeout: int = 20) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                return None
            data = r.read()
            return data or None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


# ── Naming ──────────────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    """Fold accents to ASCII first, so "Fréquence K" becomes frequence_k rather
    than fr_quence_k — the filename has to be one a person would guess."""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", folded.casefold()).strip("_") or "untitled"


def find_override(overrides_dir: Path, slug: str) -> Path | None:
    for suffix in OVERRIDE_SUFFIXES:
        candidate = overrides_dir / f"{slug}{suffix}"
        if candidate.is_file():
            return candidate
    return None


# ── Image work ──────────────────────────────────────────────────────────────


def load_font(px: int) -> ImageFont.FreeTypeFont:
    """Pillow 10.1+ bundles a scalable font, so nothing has to be shipped or
    found on the host."""
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        for path in (
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ):
            if Path(path).is_file():
                return ImageFont.truetype(path, px)
        return ImageFont.load_default()


def initials(name: str) -> str:
    words = [w for w in re.split(r"[\s\-_/]+", name) if w and w[0].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def monogram(name: str, px: int) -> Image.Image:
    """A placeholder that reads as a design choice rather than a failure: the
    hue is derived from the name, so every tile differs and the same item is
    the same colour every time."""
    h = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    bg = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.45, 0.40))
    fg = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.12, 0.96))

    img = Image.new("RGB", (px, px), bg)
    draw = ImageDraw.Draw(img)
    text = initials(name)
    font = load_font(int(px * 0.42))
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((px - (box[2] - box[0])) / 2 - box[0], (px - (box[3] - box[1])) / 2 - box[1]),
        text,
        font=font,
        fill=fg,
    )
    return img


def normalize(
    data: bytes, px: int, mat: tuple[int, int, int], inset: int = 0
) -> Image.Image | None:
    """Fit onto a square mat, padded rather than cropped, and flattened.

    Padding is invisible when mat matches the tile behind it, and flattening
    here is the only chance to do it: MA's proxy does not expose the flatten
    argument, and on the device an alpha channel left unhandled paints whatever
    undefined RGB sits under transparent pixels.
    """
    try:
        src = Image.open(io.BytesIO(data))
        src.load()
    except Exception:
        return None

    src = src.convert("RGBA")
    fit = px - 2 * inset
    scale = min(fit / src.width, fit / src.height)
    size = (max(1, round(src.width * scale)), max(1, round(src.height * scale)))
    src = src.resize(size, Image.LANCZOS)

    canvas = Image.new("RGB", (px, px), mat)
    canvas.paste(src, ((px - size[0]) // 2, (px - size[1]) // 2), src)
    return canvas


def round_corners(img: Image.Image, radius: int, mat: tuple[int, int, int]):
    """Give every tile the same card silhouette.

    Most station logos are opaque with backgrounds of their own — often white —
    so a grid of them against a dark UI reads as a jumble of mismatched
    rectangles. A shared rounded edge makes the differing backgrounds look like
    label art on a consistent card instead.
    """
    if radius <= 0:
        return img
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255
    )
    base = Image.new("RGB", img.size, mat)
    base.paste(img, (0, 0), mask)
    return base


GALLERY_CSS = """
:root { color-scheme: dark }
body { margin:0; padding:28px 20px 60px; background:#121212; color:#e8e8e8;
  font:15px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif }
.wrap { max-width:960px; margin:0 auto }
h1 { font-size:21px; margin:0 0 4px } h2 { font-size:15px; margin:34px 0 10px;
  text-transform:uppercase; letter-spacing:.09em; color:#8a8a8a; font-weight:600 }
p { color:#b4b4b4; margin:0 0 14px } code { font-family:ui-monospace,Menlo,monospace;
  background:#1e1e1e; padding:2px 6px; border-radius:5px; font-size:13px; color:#eee }
ol { color:#b4b4b4; padding-left:20px } ol li { margin:7px 0 }
.grid { display:grid; gap:16px; grid-template-columns:repeat(auto-fill,minmax(132px,1fr)) }
.card { background:#1a1a1a; border-radius:10px; padding:12px; text-align:center }
.card img { width:84px; height:84px; image-rendering:auto; border-radius:10px }
.name { font-size:13px; margin:9px 0 5px; word-break:break-word; color:#e8e8e8 }
.file { font-family:ui-monospace,Menlo,monospace; font-size:11px; color:#8a8a8a;
  word-break:break-all; -webkit-user-select:all; user-select:all }
.badge { display:inline-block; font-size:10px; letter-spacing:.06em; padding:2px 7px;
  border-radius:20px; text-transform:uppercase; margin-bottom:6px }
.gen { background:#4a3410; color:#ffb02e } .ma { background:#1e1e1e; color:#777 }
.own { background:#123420; color:#4cd964 }
.note { background:#1a1a1a; border-left:3px solid #0095ff; padding:12px 16px;
  border-radius:0 8px 8px 0; margin:18px 0 }
@media (prefers-color-scheme: light) {
  body { background:#fff; color:#1a1a1a } .card,.note { background:#f4f4f5 }
  code { background:#eee; color:#222 } p,ol,.file { color:#555 }
}
"""


def write_gallery(out_dir: Path, manifest: list[dict], overrides_dir: Path, px: int):
    """A page at the same URL the panel reads from, so a user who is looking at
    a generated tile can find out what to name their replacement without
    opening a terminal."""
    gaps = [m for m in manifest if m["artwork"] == "monogram"]
    badge = {
        "monogram": ('gen', 'generated'),
        "music_assistant": ('ma', 'Music Assistant'),
        "override": ('own', 'your image'),
    }

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def cards(rows):
        return "\n".join(
            f'<div class="card"><img src="{m["file"]}?v={m["v"]}" alt="" width="{px}" '
            f'height="{px}"><div class="badge {badge[m["artwork"]][0]}">'
            f'{badge[m["artwork"]][1]}</div><div class="name">{esc(m["name"])}</div>'
            f'<div class="file">{m["slug"]}.png</div></div>'
            for m in rows
        )

    gap_section = ""
    if gaps:
        gap_section = f"""
<h2>{len(gaps)} without artwork</h2>
<p>Music Assistant has no image for these, so the panel is showing initials.
To replace one, save your image as the filename under its tile.</p>
<div class="grid">{cards(gaps)}</div>"""

    rest = [m for m in manifest if m["artwork"] != "monogram"]
    rest_section = ""
    if rest:
        rest_section = f"""
<h2>{len(rest)} with artwork</h2>
<p>These came from Music Assistant, or from an image you supplied. Adding a
file for any of them replaces what is here — yours always wins.</p>
<div class="grid">{cards(rest)}</div>"""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ma-bar artwork</title><style>{GALLERY_CSS}</style></head>
<body><div class="wrap">
<h1>ma-bar artwork</h1>
<p>Every tile the panel can show, {px}&times;{px}. Tap a filename to select it.</p>
<div class="note"><strong>To replace a tile</strong>
<ol>
<li>Save your image as the filename shown under it. Any size or shape,
    <code>.png</code> <code>.jpg</code> <code>.webp</code> <code>.gif</code>.</li>
<li>Put it in <code>{esc(str(overrides_dir))}</code></li>
<li>Run the normalizer again, or press <em>Refresh artwork</em> in Home Assistant.</li>
</ol>
The panel updates on its next page turn. No reflash, no restart.</div>
{gap_section}{rest_section}
</div></body></html>"""
    (out_dir / "index.html").write_text(html)


def parse_color(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


# ── Gathering items ─────────────────────────────────────────────────────────


def gather(ma: MusicAssistant, sections: list[dict]) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    for section in sections:
        media_type = section["media_type"]
        source = section.get("source", "favorites")
        limit = section.get("limit", 100)

        if source == "list":
            found = []
            for entry in section.get("items", []):
                name = entry["name"] if isinstance(entry, dict) else entry
                pinned = entry.get("uri") if isinstance(entry, dict) else None
                hit = ma.find(name, media_type)
                if hit is None and pinned is None:
                    found.append({"name": name, "uri": None, "raw": {}})
                    continue
                found.append(
                    {
                        "name": (hit or {}).get("name", name),
                        "uri": pinned or hit.get("uri"),
                        "raw": hit or {},
                    }
                )
        else:
            raw = ma.library(media_type, favorite=(source == "favorites"), limit=limit)
            found = [
                {"name": i.get("name", ""), "uri": i.get("uri"), "raw": i} for i in raw
            ]

        for f in found:
            f["media_type"] = media_type
            f["section"] = section.get("name", media_type)
            f["slug"] = slugify(f["name"])
            if f["slug"] in seen:
                continue
            seen.add(f["slug"])
            items.append(f)

    return items


# ── Main ────────────────────────────────────────────────────────────────────


def read_secret(path: Path, key: str) -> str:
    if not path.is_file():
        sys.exit(f"error: {path} not found — copy secrets.yaml.example and fill it in")
    data = yaml.safe_load(path.read_text()) or {}
    if key not in data:
        sys.exit(f"error: {key} not found in {path}")
    return str(data[key])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "ma-bar.config.yaml")
    ap.add_argument("--secrets", type=Path, default=REPO / "secrets.yaml")
    ap.add_argument("--out", type=Path, help="override artwork.output_dir")
    ap.add_argument("--report", action="store_true", help="show sources, write nothing")
    ap.add_argument("--force", action="store_true", help="rewrite unchanged tiles")
    args = ap.parse_args()

    if not args.config.is_file():
        sys.exit(f"error: {args.config} not found — copy ma-bar.config.example.yaml")
    cfg = yaml.safe_load(args.config.read_text())

    art = cfg.get("artwork", {})
    px = art.get("tile_px", 84)
    mat = parse_color(art.get("mat_color", "#1E1E1E"))
    proxy_size = art.get("proxy_size", 256)
    radius = art.get("corner_radius", 10)
    inset = art.get("inset", 0)
    overrides_dir = Path(art.get("overrides_dir", REPO / "overrides"))
    if not overrides_dir.is_absolute():
        overrides_dir = (args.config.parent / overrides_dir).resolve()
    out_dir = args.out or Path(art["output_dir"])

    ma = MusicAssistant(
        cfg["music_assistant"]["url"], read_secret(args.secrets, "ma_api_token")
    )

    items = gather(ma, cfg["sections"])
    print(f"{len(items)} items across {len(cfg['sections'])} sections\n")

    if not args.report:
        out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    counts = {"override": 0, "music_assistant": 0, "monogram": 0}

    for item in items:
        slug = item["slug"]
        source = None
        image = None

        override = find_override(overrides_dir, slug)
        if override:
            image = normalize(override.read_bytes(), px, mat, inset)
            if image is None:
                print(f"  ! {slug}: override {override.name} is not a readable image")
            else:
                source = "override"

        if image is None and item["raw"]:
            url = ma.artwork_url(item["raw"], proxy_size)
            if url:
                data = fetch(url)
                if data:
                    image = normalize(data, px, mat, inset)
                    if image is not None:
                        source = "music_assistant"

        if image is None:
            image = monogram(item["name"], px)
            source = "monogram"

        image = round_corners(image, radius, mat)

        counts[source] += 1
        target = out_dir / f"{slug}.png"

        buf = io.BytesIO()
        image.save(buf, "PNG", optimize=True)
        payload = buf.getvalue()
        # The device only refetches when a URL changes, so the URL has to carry
        # a fingerprint of the bytes. Swap in a new override, this moves, and
        # the panel picks it up on the next page turn without a reflash.
        version = hashlib.sha256(payload).hexdigest()[:8]

        if not args.report:
            if args.force or not target.is_file() or target.read_bytes() != payload:
                target.write_bytes(payload)

        manifest.append(
            {
                "name": item["name"],
                "slug": slug,
                "media_type": item["media_type"],
                "section": item["section"],
                "uri": item["uri"],
                "artwork": source,
                "file": f"{slug}.png",
                "v": version,
            }
        )

        mark = {"override": "own", "music_assistant": "MA ", "monogram": "gen"}[source]
        flag = "" if item["uri"] else "   (unresolved)"
        print(f"  {mark}  {slug:<34} {item['media_type']:<9}{flag}")

    print(
        f"\n{counts['override']} from your overrides, "
        f"{counts['music_assistant']} from Music Assistant, "
        f"{counts['monogram']} generated"
    )

    known = {m["slug"] for m in manifest}
    orphans = sorted(
        f.name
        for f in overrides_dir.glob("*")
        if f.suffix.lower() in OVERRIDE_SUFFIXES and f.stem not in known
    )
    if orphans:
        print(
            f"\n{len(orphans)} override file(s) match no item in your library.\n"
            f"Renaming an item in Music Assistant changes its slug, so an "
            f"override\nkeeps the old name and stops being used. Rename the "
            f"file to match:"
        )
        for name in orphans:
            print(f"    {name}")

    gaps = [m for m in manifest if m["artwork"] == "monogram"]
    if gaps:
        print(
            f"\nTo replace a generated tile, drop an image in {overrides_dir}\n"
            f"named after its slug, then run this again:"
        )
        for m in gaps[:10]:
            print(f"    {m['slug']}.png     ({m['name']})")
        if len(gaps) > 10:
            print(f"    ... and {len(gaps) - 10} more")

    if not args.report:
        (out_dir / "manifest.json").write_text(
            json.dumps(
                {
                    # The firmware is built for one tile size. If these disagree
                    # the artwork is the wrong shape and the device starts
                    # reallocating buffers again, so the Home Assistant package
                    # checks this before pushing any URL.
                    "tile_px": px,
                    "corner_radius": radius,
                    "counts": counts,
                    "items": manifest,
                },
                indent=2,
            )
        )
        write_gallery(out_dir, manifest, overrides_dir, px)
        print(
            f"\nwrote {len(manifest)} tiles, manifest.json and index.html to {out_dir}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
