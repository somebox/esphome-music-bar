"""Unit tests for the artwork normalizer's pure functions.

Nothing here touches the network or Music Assistant. The live behaviour that
cannot be asserted without a real instance is listed in docs/plan.md.
"""

from __future__ import annotations

import io
import urllib.error

import pytest
from PIL import Image

from conftest import na

MAT = (0x1E, 0x1E, 0x1E)


# ── Naming ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("WKCR", "wkcr"),
        ("Radio Meuh", "radio_meuh"),
        # Accents fold to ASCII so the filename is one a person would guess,
        # rather than fr_quence_k.
        ("Fréquence K", "frequence_k"),
        ("70s Manhattan Club", "70s_manhattan_club"),
        ("100 Days, 100 Nights", "100_days_100_nights"),
        ("!!!", "untitled"),
        ("  spaced  out  ", "spaced_out"),
    ],
)
def test_slugify(name, expected):
    assert na.slugify(name) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("WKCR", "WK"),
        ("Radio Meuh", "RM"),
        ("Kind of Blue", "KO"),
        ("A", "A"),
        ("!!!", "?"),
    ],
)
def test_initials(name, expected):
    assert na.initials(name) == expected


# ── The shared hash ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        # Published FNV-1a 32-bit test vectors. If these move, the device and
        # the script have diverged from the standard and from each other.
        ("", 0x811C9DC5),
        ("a", 0xE40C292C),
        ("foobar", 0xBF9CF968),
    ],
)
def test_fnv1a_reference_vectors(text, expected):
    assert na.fnv1a(text) == expected


def test_monogram_colors_are_deterministic():
    assert na.monogram_colors("WKCR") == na.monogram_colors("WKCR")


def test_monogram_colors_differ_between_items():
    names = ["WKCR", "Radio Meuh", "France Musique", "Big Blue Swing", "BBC 6"]
    backgrounds = {na.monogram_colors(n)[0] for n in names}
    # A page of identical placeholders reads as breakage; the whole point of
    # hashing the name is that a page of them reads as a design.
    assert len(backgrounds) == len(names)


def test_monogram_is_the_tile_size():
    img = na.monogram("Radio Meuh", 84)
    assert img.size == (84, 84)
    assert img.mode == "RGB"


# ── Image normalization ─────────────────────────────────────────────────────


def encode(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


@pytest.mark.parametrize(
    "size",
    [
        (57, 57),  # all four observed on the reference station library
        (150, 150),
        (160, 138),
        (160, 76),
        (1400, 520),  # the deliberately awkward override
        (8, 3000),
    ],
)
def test_every_source_shape_becomes_one_square(size):
    """The whole reason this script exists. ESPHome frees and reallocates a
    runtime image's buffer whenever the decoded dimensions change, so a mix of
    shapes fragments PSRAM across page turns."""
    out = na.normalize(encode(Image.new("RGB", size, (200, 30, 30))), 84, MAT)
    assert out.size == (84, 84)
    assert out.mode == "RGB"


def test_alpha_is_flattened_onto_the_mat():
    """MA's proxy does not expose a flatten argument, and an alpha channel left
    unhandled paints whatever undefined RGB sits under transparent pixels."""
    src = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    out = na.normalize(encode(src), 84, MAT)
    assert out.mode == "RGB"
    assert out.getpixel((42, 42)) == MAT


def test_padding_uses_the_mat_colour():
    # A wide source leaves bars top and bottom; they have to be invisible
    # against the tile behind them.
    out = na.normalize(encode(Image.new("RGB", (160, 40), (255, 255, 255))), 84, MAT)
    assert out.getpixel((42, 1)) == MAT


def test_unreadable_bytes_return_none():
    assert na.normalize(b"not an image", 84, MAT) is None


def test_round_corners_paints_corners_with_the_mat():
    solid = Image.new("RGB", (84, 84), (255, 255, 255))
    out = na.round_corners(solid, 10, MAT)
    assert out.getpixel((0, 0)) == MAT
    assert out.getpixel((42, 42)) == (255, 255, 255)


def test_round_corners_radius_zero_is_a_passthrough():
    solid = Image.new("RGB", (84, 84), (255, 255, 255))
    assert na.round_corners(solid, 0, MAT).getpixel((0, 0)) == (255, 255, 255)


# ── Fetch classification ────────────────────────────────────────────────────
#
# Separating "MA says there is no artwork" from "MA could not be reached" is
# what stops an outage from replacing every real tile with a monogram.


def fake_urlopen(behaviour):
    def _open(url, timeout=0):
        raise behaviour

    return _open


def test_404_is_an_answer_not_an_outage(monkeypatch):
    """A proxy_id is returned even when there is no artwork, and the proxy 404s
    for those. That is MA telling us to draw a monogram."""
    err = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    monkeypatch.setattr(na.urllib.request, "urlopen", fake_urlopen(err))
    got = na.fetch("http://example/x")
    assert got.data is None
    assert got.transient is False


def test_server_error_says_nothing(monkeypatch):
    err = urllib.error.HTTPError("u", 503, "Unavailable", {}, None)
    monkeypatch.setattr(na.urllib.request, "urlopen", fake_urlopen(err))
    assert na.fetch("http://example/x").transient is True


def test_connection_refused_says_nothing(monkeypatch):
    err = urllib.error.URLError(OSError("Connection refused"))
    monkeypatch.setattr(na.urllib.request, "urlopen", fake_urlopen(err))
    assert na.fetch("http://example/x").transient is True


# ── Gathering, and slug collisions ──────────────────────────────────────────


class FakeMA:
    """Enough of MusicAssistant to exercise gather()."""

    def __init__(self, library):
        self.library_data = library

    def library(self, media_type, favorite, limit):
        return self.library_data.get(media_type, [])[:limit]

    def find(self, name, media_type):
        for item in self.library_data.get(media_type, []):
            if item["name"].casefold() == name.casefold():
                return item
        return None


def item(name, uri):
    return {"name": name, "uri": uri}


def test_search_result_keys_are_plural_except_radio():
    """music/search returns artists / albums / tracks / playlists / radio.
    Looking up "album" finds nothing, which silently left every non-radio
    `list` section unresolved."""
    assert na.RESULT_KEY["album"] == "albums"
    assert na.RESULT_KEY["playlist"] == "playlists"
    assert na.RESULT_KEY["radio"] == "radio"


def test_same_item_in_two_sections_is_deduplicated():
    ma = FakeMA({"radio": [item("WKCR", "library://radio/17")]})
    sections = [
        {"name": "A", "media_type": "radio", "source": "all"},
        {"name": "B", "media_type": "radio", "source": "all"},
    ]
    items, collisions = na.gather(ma, sections)
    assert [i["slug"] for i in items] == ["wkcr"]
    assert collisions == []


def test_same_name_in_two_media_types_keeps_both_tiles():
    """Names only have to be unique within a media type, but a slug is the
    artwork filename and those share one namespace. Dropping the second is a
    tile that silently vanishes."""
    ma = FakeMA(
        {
            "radio": [item("Blue", "library://radio/1")],
            "album": [item("Blue", "library://album/9")],
        }
    )
    sections = [
        {"name": "Radio", "media_type": "radio", "source": "all"},
        {"name": "Albums", "media_type": "album", "source": "all"},
    ]
    items, collisions = na.gather(ma, sections)
    assert [i["slug"] for i in items] == ["blue", "blue_album"]
    assert len(collisions) == 1
    assert "blue_album.png" in collisions[0]


def test_a_name_that_resolves_to_nothing_still_gets_a_tile():
    """A silently missing tile is a gap the user has to notice. An unresolved
    one is visible."""
    ma = FakeMA({"album": []})
    sections = [
        {
            "name": "Albums",
            "media_type": "album",
            "source": "list",
            "items": ["Nothing By This Name"],
        }
    ]
    items, _ = na.gather(ma, sections)
    assert len(items) == 1
    assert items[0]["uri"] is None


# ── Rename healing ──────────────────────────────────────────────────────────
#
# Music Assistant 2.9.0 made renaming manually added stations, tracks and
# playlists a supported operation, so an orphaned override went from a rare
# accident to something users are invited to cause.


def gap(slug, name):
    return {"slug": slug, "name": name, "artwork": "monogram"}


def test_a_near_miss_is_offered_as_a_rename():
    renames = na.suggest_renames(
        ["radio_meuh.png"], [gap("radio_meuh_fm", "Radio Meuh FM")]
    )
    assert renames == [("radio_meuh.png", "radio_meuh_fm.png")]


def test_an_orphan_resembling_nothing_is_not_guessed_at():
    """A confident wrong suggestion is worse than none."""
    assert na.suggest_renames(["wkcr.png"], [gap("bbc_radio_3", "BBC Radio 3")]) == []


def test_no_gaps_means_no_suggestions():
    assert na.suggest_renames(["wkcr.png"], []) == []


def test_one_gap_is_not_offered_to_two_orphans():
    renames = na.suggest_renames(
        ["radio_meuh.png", "radio_meuf.png"], [gap("radio_meuh_fm", "Radio Meuh FM")]
    )
    assert len(renames) == 1


def test_an_explicit_uri_pins_an_ambiguous_name():
    ma = FakeMA({"album": []})
    sections = [
        {
            "name": "Albums",
            "media_type": "album",
            "source": "list",
            "items": [{"name": "Greatest Hits", "uri": "library://album/412"}],
        }
    ]
    items, _ = na.gather(ma, sections)
    assert items[0]["uri"] == "library://album/412"
