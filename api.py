from re import M
import requests
import time
BASE_URL = "https://api.henrikdev.xyz"
BASE_BACKOFF_DELAY = 2
MAX_ATTEMPTS = 3
MIN_GAP_SECONDS = 2.0

_last_request_at = None 


class ApiError(Exception):
    """Base for every failure raised by this module."""


class AccountNotFound(ApiError):
    """Raised when the RIOT ID does not exist (404)
    
    The config is wrong and a person has to fix it, so retrying is pointless. 
    Skip that accound and carry on with the rest.
    """


class InvalidApiKey(ApiError):
    """Raised when the API key has been rejected (401)
    
    Every remaining request will fail in the same way, so the caller should stop
    rather than work through the other accounts.
    """


class RequestFailed(ApiError):
    """Raised when a request keeps failing after MAX_ATTEMPTS (429, 5xx, timeouts)
    
    Nothing is wrong with the request, so a later run might succeed.
    """

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

    for attempt in range(1,MAX_ATTEMPTS+1):
        if _last_request_at is None:
            sleep_time = 0.0
        else:
            sleep_time = MIN_GAP_SECONDS - (time.monotonic() - _last_request_at)

        if sleep_time > 0:
            time.sleep(sleep_time)

        _last_request_at = time.monotonic() 
        response = requests.get(url,headers={"Authorization": api_key},params=params,timeout=(5,15)) #tuple (5,15) is used for the time out. 5s to connect(connection time out), 15s to read (how long youll wait for the server to produce an answer)
        status_code = response.status_code


        if status_code == 401:
            raise InvalidApiKey("The API key you sent has been rejected")
        if status_code == 404:
            raise AccountNotFound


        if (status_code == 429 or status_code >= 500):
            if attempt < MAX_ATTEMPTS:
                exponential_wait_time = BASE_BACKOFF_DELAY ** attempt
                try:
                    servers_wait_time = response.headers.get("Retry-After")
                    if servers_wait_time is None:
                        time.sleep(exponential_wait_time)
                    else:
                        time.sleep(int(servers_wait_time))
                except ValueError:
                    time.sleep(int(servers_wait_time))
            continue
        
        return response.json()["data"]
    
    raise RequestFailed(f"Requests failed after the {MAX_ATTEMPTS} attempts, with status code: {status_code}")
        



    ...