import os

import tomllib
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when a config file is missing, malformed or incomplete.

    A person has to fix the file, so there is nothing for the caller to retry.
    """


def _read_toml(path):
    """Parse a TOML file, raising ConfigError for anything that stops it parsing.

    open() raises OSError when the file is missing or unreadable, and tomllib
    raises TOMLDecodeError when the syntax is wrong. Both are failures a person
    fixes in a file, which is what ConfigError means, so they are re-raised as
    one type rather than leaking two more for every caller to handle. The
    original exception is chained with "from", so the traceback still shows the
    line and column tomllib objected to.
    """

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

    These are the competitive maps prefilled into the maps lookup table, so
    the dashboard can offer a map with no matches yet. Ingestion still
    inserts any other map it meets, so this list controls what is offered,
    not what the database accepts.

    Raises ConfigError if the file is missing or is not valid TOML, if it has
    no [[maps]] entries, if "maps" is not an array of tables, if an entry is
    missing an id or name, or if two entries share an id. The duplicate check
    belongs here rather than in the database, because the write path uses
    ON CONFLICT DO NOTHING and would skip the second row silently. Duplicate
    names are allowed: the content endpoint lists two different maps both
    called "The Range".
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

    load_dotenv() copies .env into os.environ, so the same code works where
    the variable is set by the environment instead and no .env file exists.
    A missing file is not an error on its own: it shows up as a missing key.

    Raises ConfigError if HENRIK_KEY is unset or empty. Whitespace is stripped
    from the value, since a stray space would otherwise reach the
    Authorization header and come back as a 401.
    """

    load_dotenv()
    henrik_key = os.getenv("HENRIK_KEY", "")

    if not henrik_key:
        raise ConfigError(
            "Either the .env file might be missing or the file exists without a HENRIK_KEY line."
        )

    return henrik_key.strip()
