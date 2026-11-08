import os
import pathlib

import tomllib
from dotenv import load_dotenv

# Every path is built from this module's own location, so the scripts work
# from any working directory.
ROOT = pathlib.Path(__file__).parent

DB_PATH = ROOT / "valstats.db"
CONFIG_PATH = ROOT / "accounts.toml"
MAP_PATH = ROOT / "maps.toml"
OUT_PATH = ROOT / "worker" / "stats.sql"


class ConfigError(Exception):
    """Raised when a config file is missing, malformed or incomplete."""


def _read_toml(path):
    """Parse a TOML file, raising ConfigError for anything that stops it parsing."""

    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError as error:
        raise ConfigError(f"{path}: file not found") from error
    except OSError as error:
        raise ConfigError(f"{path}: could not be read: {error.strerror}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: not valid TOML: {error}") from error


def load_accounts(path):
    """Read the accounts config and return a list of (name, tag) pairs.

    Raises ConfigError if the file is missing or is not valid TOML, if it has
    no [[accounts]] entries, if "accounts" is not an array of tables, or if any
    entry is missing a name or tag. Empty strings count as missing, since an
    empty name would resolve to a 404 at the API rather than failing here.
    """

    account_list = []

    data = _read_toml(path)
    accounts = data.get("accounts")

    if not accounts:
        raise ConfigError(f"{path}: no [[accounts]] entries found")

    if not isinstance(accounts, list):
        raise ConfigError(
            f"{path}: expected [[accounts]] entries, "
            f"but found a {type(accounts).__name__}."
        )

    for position, account in enumerate(accounts, start=1):
        name = account.get("name")
        if not name:
            raise ConfigError(f"{path}: entry {position}: name is missing or empty.")

        tag = account.get("tag")
        if not tag:
            raise ConfigError(
                f"{path}: entry {position}: {name}'s tag is missing or empty."
            )

        account_list.append((name, tag))

    return account_list


def load_maps(path):
    """Read the map allowlist and return a list of (map_id, name) pairs.

    Raises ConfigError if the file is missing or is not valid TOML, if it has
    no [[maps]] entries, if an entry is missing an id or name, or if two entries
    share an id. The duplicate check belongs here rather than in the database,
    because the write path uses ON CONFLICT DO NOTHING and would skip the second
    row silently.
    """

    map_list = []
    id_list = set()

    data = _read_toml(path)
    val_maps = data.get("maps")

    if not val_maps:
        raise ConfigError(f"{path}: no [[maps]] entries found")

    if not isinstance(val_maps, list):
        raise ConfigError(
            f"{path}: expected [[maps]] entries, "
            f"but found a {type(val_maps).__name__}."
        )

    for position, val_map in enumerate(val_maps, start=1):
        map_name = val_map.get("name")
        if not map_name:
            raise ConfigError(f"{path}: entry {position}: name is missing or empty.")

        map_id = val_map.get("id")
        if not map_id:
            raise ConfigError(f"{path}: entry {position}: id is missing or empty.")

        if map_id in id_list:
            raise ConfigError(
                f"{path}: entry {position}: "
                f"id {map_id} is already used by an earlier entry."
            )
        id_list.add(map_id)

        map_list.append((map_id, map_name))

    return map_list


def load_api_key():
    """Return the HenrikDev API key, read from .env into the environment.

    Raises ConfigError if HENRIK_KEY is unset or empty. Whitespace is stripped
    from the value, since a stray space would then reach the
    Authorization header and come back as a 401.
    """

    load_dotenv()
    henrik_key = os.getenv("HENRIK_KEY", "")

    if not henrik_key:
        raise ConfigError(
            "Either the .env file might be missing or the file exists without a HENRIK_KEY line."
        )

    return henrik_key.strip()
