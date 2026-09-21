import os

import tomllib
from dotenv import load_dotenv


# Read the TOML file. Return a list of (name, tag) pairs.
def load_accounts(path):
    # initialise the list of accounts
    accountList = []

    with open(path, "rb") as f:
        # loads the data as the tomllib
        data = tomllib.load(f)

        # checks if there are accounts in the current data and raises a ValueError if not available
        if "accounts" not in data:
            raise ValueError(f"no [[accounts]] found in {path}")
        # gets the list of all the accounts
        accounts = data["accounts"]
        # looks through the accounts and makes sure their information is filled out
        for position, account in enumerate(accounts, start=1):
            if "name" not in account:
                raise ValueError(f"{path}: account {position} has no name")
            name = account["name"]

            if "tag" not in account:
                raise ValueError(f"account {name} is missing a tag")
            tag = account["tag"]

            accountList.append((name, tag))

        return accountList


def load_api_key():
    # Reads .env and adds its entries to os.environ
    load_dotenv()

    # get the HENRIK KEY and if nothing is there it returns an empty string
    henrik_key = os.getenv("HENRIK_KEY", "")

    if not henrik_key:
        raise ValueError(
            "Either the .env file might be missing or the file exists without a HENRIK_KEY line."
        )

    return henrik_key.strip()
