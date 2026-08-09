"""The device and the script must draw the same monogram.

A tile the panel renders itself and a tile the normalizer renders to a PNG can
appear on two installs of the same project, so they have to agree on the
colour. This compiles esphome/includes/music_bar_monogram.h and diffs it against
scripts/normalize-artwork.py for a spread of names.

Change the hash on one side and this fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import na, REPO

HEADER = REPO / "esphome" / "includes" / "music_bar_monogram.h"

NAMES = [
    "WKCR",
    "Radio Meuh",
    "France Musique",
    "Big Blue Swing",
    "Kind of Blue",
    "100 Days, 100 Nights",
    "70s Manhattan Club",
    "CRB Boston Early Music",
    "Discover Weekly",
    "a",
    "",
    # Multi-byte UTF-8: the colour must still agree, because both sides hash
    # bytes rather than characters.
    "Fréquence K",
    "東京",
]

HARNESS = r"""
#include "music_bar_monogram.h"
#include <cstdio>
#include <string>
#include <vector>

int main(int argc, char **argv) {
  for (int i = 1; i < argc; i++) {
    std::string name(argv[i]);
    printf("%08x\t%06x\t%06x\t%s\n", music_bar::fnv1a(name),
           music_bar::monogram_bg_hex(name), music_bar::monogram_fg_hex(name),
           music_bar::initials(name).c_str());
  }
  return 0;
}
"""


def compiler() -> str | None:
    for candidate in ("c++", "g++", "clang++"):
        if shutil.which(candidate):
            return candidate
    return None


@pytest.fixture(scope="module")
def device(tmp_path_factory):
    cxx = compiler()
    if cxx is None:
        pytest.skip("no C++ compiler available")
    work = tmp_path_factory.mktemp("monogram")
    src = work / "harness.cpp"
    src.write_text(HARNESS)
    binary = work / "harness"
    subprocess.run(
        [cxx, "-std=c++17", "-O1", f"-I{HEADER.parent}", str(src), "-o", str(binary)],
        check=True,
        capture_output=True,
    )

    out = subprocess.run(
        [str(binary), *NAMES], check=True, capture_output=True, text=True
    ).stdout.splitlines()

    parsed = {}
    for name, line in zip(NAMES, out):
        h, bg, fg, *rest = line.split("\t")
        parsed[name] = {
            "hash": int(h, 16),
            "bg": int(bg, 16),
            "fg": int(fg, 16),
            "initials": rest[0] if rest else "",
        }
    return parsed


def as_hex(rgb) -> int:
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


@pytest.mark.parametrize("name", NAMES)
def test_hash_agrees(device, name):
    assert device[name]["hash"] == na.fnv1a(name)


@pytest.mark.parametrize("name", NAMES)
def test_colour_agrees(device, name):
    bg, fg = na.monogram_colors(name)
    assert device[name]["bg"] == as_hex(bg), f"background differs for {name!r}"
    assert device[name]["fg"] == as_hex(fg), f"foreground differs for {name!r}"


@pytest.mark.parametrize(
    "name", [n for n in NAMES if n.isascii() and any(c.isalnum() for c in n)]
)
def test_initials_agree_for_ascii_names(device, name):
    assert device[name]["initials"] == na.initials(name)


def test_non_ascii_initials_fall_back_to_a_glyph(device):
    """The device has no Unicode .upper(), so it returns "" and the caller
    shows the media-type glyph instead of a wrong letter. Documented divergence,
    asserted so it stays deliberate."""
    assert device["東京"]["initials"] == ""
    assert device[""]["initials"] == ""


def test_the_header_is_the_only_other_copy_of_the_hash():
    """If a third implementation appears, it needs adding to this test."""
    header = HEADER.read_text()
    assert "0x811C9DC5" in header
    assert "0x01000193" in header
