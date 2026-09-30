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

        # gets the list of all the accounts
        accounts = data.get("accounts")
        # checks if there are accounts in the current data and raises a ValueError if not available
        if not isinstance(accounts,list):
            raise ValueError(f"{path}: expected [[maps]] entries, but found a {type(accounts).__name__}.")
        
        # looks through the accounts and makes sure their information is filled out
        for position, account in enumerate(accounts, start=1):
            name = account.get("name")
            if not name:
                raise ValueError(f"{path}: entry {position}: name is missing or empty.")
            
            tag = account.get("tag")
            if not tag:
                raise ValueError(f"{path}: entry {position}: {name}'s tag is missing empty.")

            accountList.append((name, tag))

        return accountList

def load_maps(path):
    """Reads the toml file of the existing maps, returns their ids and names in an (id,name) tuple"""
    map_list = []
    id_list = set()

    with open(path,"rb") as f:
        data = tomllib.load(f)
        val_maps = data.get("maps")
        if not isinstance(val_maps,list):
            raise ValueError(f"{path}: expected [[maps]] entries, but found a {type(val_maps).__name__}.")
        
        maps = data["maps"]
        for position,val_map in enumerate(maps,start=1):

            map_name = val_map.get("name")
            if not map_name:
                raise ValueError(f"{path}: entry {position}: name is missing or empty.")
            
            map_id = val_map.get("id")
            if not map_id:
                raise ValueError(f"{path}: entry {position}: map_id is missing or empty.")

            if map_id in id_list:
                raise ValueError(f"{path}: entry {position}: id {map_id} is already used by an ealier entry.")
            id_list.add(map_id)

            map_list.append((map_id,map_name))
        
        return map_list
            

    

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
