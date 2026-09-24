import requests
import time
BASE_URL = "https://api.henrikdev.xyz"
MAX_ATTEMPTS = 3
MIN_GAP_SECONDS = 2.0

_last_request_at = None 


class ApiError(Exception):
    """Base for every failure raised by this module."""


class AccountNotFound(ApiError):
    """..."""


class InvalidApiKey(ApiError):
    """..."""


class RequestFailed(ApiError):
    """..."""
    
# Call the account endpoint and return the PUUID.
def fetch_account(name, tag, api_key):
    url = f"{BASE_URL}/valorant/v2/account/{name}/{tag}"
    response = requests.get(url, headers={"Authorization": api_key})
    status_code = response.status_code

    # 404: The riot id does not exist. 401: The server does not know who you are ie the api key is not recognised
    if status_code == 404:
        raise ValueError(
            f"The riot id you are looking for doesn't exist. RIOT_ID: {name}#{tag}"
        )
    if status_code == 401:
        raise ValueError("The API key you sent has been rejected")

    # To handle all other errors that aren't to do with the api key and the riot id provided
    if status_code != 200:
        raise ValueError(f"Unexpected error. Status code: {status_code}")

    data = response.json()["data"]

    return data["puuid"]

def request(path, api_key, params=None):
    """Send a GET to the API, respecting the rate limit and retrying transient failures.
    Returns the parsed response. Raises on a permanent failure or after MAX_ATTEMPTS."""

    global _last_request_at 
    url = f"{BASE_URL}/{path}"
    for attempt in range(MAX_ATTEMPTS):
        sleep_time = 2 - (time.monotonic() - _last_request_at) 
        if sleep_time > 0:
            _last_request_at = time.monotonic()
            response = requests.get(url,headers={"Authorization": api_key},params=params)
            status_code = response.status_code
            if status_code == 404 or status_code == 401:
                return status_code
                
    



    ...