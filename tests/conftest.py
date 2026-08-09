"""Make the normalizer importable.

The script is named with a hyphen so it reads as a command rather than a
module, which means it cannot be imported by name.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    path = REPO / "scripts" / "normalize-artwork.py"
    spec = importlib.util.spec_from_file_location("normalize_artwork", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["normalize_artwork"] = module
    spec.loader.exec_module(module)
    return module


na = _load()


@pytest.fixture
def norm():
    return na
