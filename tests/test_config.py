"""Tests for the config loaders.

Each fixture under tests/fixtures/ is one way a config file can be wrong.
The loaders are expected to raise ConfigError with a message naming the
file, the entry and the problem.
"""

import re
from pathlib import Path

import pytest

import config

FIXTURES = Path(__file__).parent / "fixtures"
ACCOUNTS = FIXTURES / "accounts"
MAPS = FIXTURES / "maps"


# --- the happy path, which the error cases cannot prove ---


def test_load_accounts_returns_name_tag_pairs():
    """A valid file returns a list of (name, tag) tuples, in file order."""
    result = config.load_accounts(ACCOUNTS / "valid.toml")
    assert result == [("donner kebab", "bossm"), ("the alchemist", "fmab")]


def test_load_maps_returns_id_name_pairs():
    """A valid file returns a list of (map_id, name) tuples, in file order."""
    result = config.load_maps(MAPS / "valid.toml")
    assert result == [
        ("7eaecc1b-4337-bbf6-6ab9-04b8f06b3319", "Ascent"),
        ("2c9d57ec-4431-9c5e-2939-8f9ef6dd5cba", "Bind"),
    ]


# --- load_accounts rejections ---

ACCOUNT_CASES = [
    ("empty.toml", "no [[accounts]] entries found"),
    ("empty_name.toml", ("entry 2: name is missing or empty.")),
    ("missing_name.toml", ("entry 2: name is missing or empty.")),
    ("missing_tag.toml", ("entry 1: donner kebab's tag is missing or empty.")),
    ("single_bracket.toml", ("expected [[accounts]] entries, but found a dict.")),
]


@pytest.mark.parametrize(
    "test_path,expected_error",
    ACCOUNT_CASES,
    ids=[t[0] for t in ACCOUNT_CASES],
)
def test_all_account_errors(test_path, expected_error):
    with pytest.raises(config.ConfigError, match=re.escape(expected_error)):
        config.load_accounts(ACCOUNTS / test_path)


# --- load_maps rejections ---

MAP_CASES = [
    ("empty.toml", "no [[maps]] entries found"),
    ("single_bracket.toml", "expected [[maps]] entries, but found a dict."),
    ("missing_name.toml", "entry 3: name is missing or empty."),
    ("empty_name.toml", "entry 2: name is missing or empty."),
    ("missing_id.toml", "entry 2: id is missing or empty."),
    (
        "duplicate_id.toml",
        (
            "entry 2: id 224b0a95-48b9-f703-1bd8-67aca101a61f "
            "is already used by an earlier entry."
        ),
    ),
]


@pytest.mark.parametrize(
    "test_path,expected_error",
    MAP_CASES,
    ids=[path for path, _ in MAP_CASES],
)
def test_all_map_errors(test_path, expected_error):
    """Every malformed maps fixture raises ConfigError naming the problem."""
    with pytest.raises(config.ConfigError, match=re.escape(expected_error)):
        config.load_maps(MAPS / test_path)
