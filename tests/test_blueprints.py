"""Structural checks on the Home Assistant blueprints.

These cannot prove an automation behaves correctly — only Home Assistant can do
that — but they catch the failures that are otherwise found by importing a
blueprint and watching nothing happen: a malformed file, a trigger the firmware
never fires, an action the firmware does not expose, or a variable referenced
before it is defined.

The firmware is the source of truth for both halves of the contract: the events
it fires and the API actions it accepts are parsed straight out of the YAML.
"""

from __future__ import annotations

import re

import pytest
import yaml

from conftest import REPO

BLUEPRINTS = sorted((REPO / "blueprints").rglob("*.yaml"))
BASE = REPO / "esphome" / "music-bar.base.yaml"


class HALoader(yaml.SafeLoader):
    """Home Assistant's !input tag is not YAML anyone else knows about."""


for tag in ("!input", "!secret", "!include"):
    HALoader.add_constructor(tag, lambda loader, node: f"<{node.value}>")


def load(path):
    return yaml.load(path.read_text(), Loader=HALoader)


@pytest.fixture(scope="module")
def firmware_contract():
    """The events the panel fires, and the actions it accepts.

    Read as text rather than parsed as YAML: the base is an ESPHome config full
    of !lambda tags and ${substitutions}, and only these two lists are wanted.
    """
    text = BASE.read_text()
    events = set(re.findall(r"event:\s*(esphome\.[a-z_]+)", text))
    actions = set(re.findall(r"^\s*- action:\s*([a-z_]+)\s*$", text, re.MULTILINE))
    return events, actions


def test_blueprints_exist():
    assert BLUEPRINTS, "no blueprints found"


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_blueprint_is_well_formed(path):
    doc = load(path)
    bp = doc["blueprint"]
    assert bp["name"].startswith("Music Bar"), "name should identify the project"
    assert bp["domain"] == "automation"
    assert bp["description"].strip(), "an undescribed blueprint is unusable"
    assert bp["input"], "no inputs means nothing to configure"
    assert doc.get("triggers"), "an automation with no trigger never runs"


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_variables_are_defined_before_use(path):
    """Home Assistant evaluates `variables:` top to bottom. Referencing a later
    one yields an empty string rather than an error, which surfaces as a
    service call to `esphome._page` and no clue why."""
    doc = load(path)
    variables = doc.get("variables")
    if not variables:
        pytest.skip("no top-level variables")

    defined: set[str] = set()
    for name, value in variables.items():
        for referenced in re.findall(r"\{\{\s*([a-z_][a-z0-9_]*)", str(value)):
            if referenced in variables and referenced not in defined:
                pytest.fail(f"{name!r} uses {referenced!r} before it is defined")
        defined.add(name)


def test_every_event_the_panel_fires_is_handled(firmware_contract):
    """A firmware event nobody listens for is a button that does nothing."""
    events, _ = firmware_contract
    handled = set()
    for path in BLUEPRINTS:
        for trigger in load(path).get("triggers", []):
            if trigger.get("trigger") == "event":
                handled.add(trigger["event_type"])
    assert events, "no events found in the firmware"
    assert events <= handled, f"fired but unhandled: {sorted(events - handled)}"


def test_every_action_a_blueprint_calls_exists_on_the_device(firmware_contract):
    """The mirror image: a blueprint calling an action the firmware does not
    define fails at runtime with a service-not-found the user has to dig for."""
    _, actions = firmware_contract
    called = set()
    for path in BLUEPRINTS:
        for match in re.findall(r'esphome\.\{\{[^}]+\}\}_([a-z_]+)"', path.read_text()):
            called.add(match)
    assert called, "no device actions called by any blueprint"
    assert called <= actions, f"called but undefined: {sorted(called - actions)}"


def test_the_handshake_is_answered():
    """The panel reports itself unconfigured until something answers hello.
    This is the single most load-bearing exchange in the project."""
    answered = False
    for path in BLUEPRINTS:
        text = path.read_text()
        if "esphome.music_bar_hello" in text and "_hello_ack" in text:
            answered = True
    assert answered, "nothing answers the boot handshake"


def test_tiles_per_page_matches_the_firmware():
    """Five is fixed in the LVGL layout — widgets are created at compile time,
    so a blueprint sending six would silently drop one."""
    favorites = next(p for p in BLUEPRINTS if p.name == "favorites.yaml")
    assert load(favorites)["variables"]["page_size"] == 5


# ── Action-syntax shapes Home Assistant rejects at load ─────────────────────
#
# These are not style checks. Each one shipped at least once and produced a
# "Message malformed" that only appears when a user imports the blueprint —
# nothing in the repo catches it otherwise, because the file is valid YAML.


def walk_actions(node):
    """Every mapping in the document, wherever it is nested."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_actions(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_actions(item)


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_if_actions_take_conditions_directly(path):
    """`if:` is a list of conditions with `then:` as a sibling key.

    Writing `if: {conditions: [...], then: [...]}` is valid YAML and invalid
    Home Assistant: it fails with "Unexpected value for condition: 'None'".
    """
    for node in walk_actions(load(path)):
        if "if" not in node:
            continue
        assert isinstance(node["if"], list), (
            "`if:` must be a list of conditions, not a mapping — `then:` is a "
            "sibling key of `if:`, not a key inside it"
        )
        assert "then" in node, "`if:` without a sibling `then:`"


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_choose_branches_are_well_formed(path):
    for node in walk_actions(load(path)):
        if "choose" not in node:
            continue
        assert isinstance(node["choose"], list)
        for option in node["choose"]:
            assert "conditions" in option and "sequence" in option, (
                "each choose option needs conditions and sequence"
            )
        # `default:` belongs beside `choose:`, not inside one of its options.
        for option in node["choose"]:
            assert "default" not in option, "`default:` is a sibling of `choose:`"


def test_page_data_is_built_from_flat_string_lists():
    """Values sent to the panel must survive Home Assistant's template
    round trip.

    A rendered template is parsed back into a value by evaluating it as a
    literal. Lists of plain strings always survive that; lists of Music
    Assistant item dictionaries need not, and a value that fails to parse stays
    a string — which the panel's service schema rejects with "expected a list
    for dictionary value @ data['names']", naming the symptom and not the cause.

    So the blueprint builds flat lists of strings and slices them, rather than
    carrying item dictionaries through to the service call.
    """
    favorites = next(p for p in BLUEPRINTS if p.name == "favorites.yaml")
    text = favorites.read_text()
    assert "map(attribute=" not in text, (
        "mapping an attribute over item dictionaries in service data is what "
        "broke this before — build flat lists of strings instead"
    )
