import sys

import api
import config
import db

DB_PATH = "valstats.db"
CONFIG_PATH = "accounts.toml"


def resolve_account(conn, name, tag, api_key):
    """Checks the cache first. If it is a miss then it calls the api, saves the result, and returns the PUUID."""
    cached_puuid = db.find_puuid(conn, name, tag)
    if cached_puuid:
        return cached_puuid
    else:
        fetched_puuid = api.fetch_account(name, tag, api_key)
        db.save_account(conn, fetched_puuid, name, tag)
        return fetched_puuid


def main():
    """Loads the config and api-key, opens the database then resolves every account. If one account fails it reports it then continues with the rest. Exits with a non zero value if any account failed."""
    api_key = config.load_api_key()
    accounts = config.load_accounts(CONFIG_PATH)
    conn = db.connect(DB_PATH)
    db.create_accounts_table(conn)

    failures = 0
    for name, tag in accounts:
        try:
            resolve_account(conn, name, tag, api_key)
            print(f"{name}#{tag} Resolved")
        except ValueError as e:
            print(f" ERROR: {name}#{tag}: {e}", file=sys.stderr)
            failures += 1
        except (api.AccountNotFound, api.RequestFailed) as e:
            print(f" ERROR: {name}#{tag}: {e}", file=sys.stderr)
            failures += 1
        except api.InvalidApiKey as e:
            print(f" ERROR: {e}", file=sys.stderr)
            conn.close()
            sys.exit(1)

    

    if failures > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
