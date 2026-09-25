import requests
import time
BASE_URL = "https://api.henrikdev.xyz"
BASE_BACKOFF_DELAY = 2
MAX_ATTEMPTS = 3
MIN_RATE_LIMIT_SPACING_SECONDS = 2.0
MAX_RETRY_AFTER_SECONDS = 60.0
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
    path = f"valorant/v2/account/{name}/{tag}"
    data = request(path,api_key,{"name": name, "tag": tag})
    return data["puuid"]

def request(path, api_key, params=None):
    """Send a GET to the API, respecting the rate limit and retrying transient failures.
    Returns the parsed response. Raises on a permanent failure or after MAX_ATTEMPTS."""

    global _last_request_at 
    url = f"{BASE_URL}/{path}"


    for attempt in range(1, MAX_ATTEMPTS + 1):

        if _last_request_at is None:
            sleep_time = 0.0
        else:
            sleep_time = MIN_RATE_LIMIT_SPACING_SECONDS - (time.monotonic() - _last_request_at)

        if sleep_time > 0:
            time.sleep(sleep_time)

        _last_request_at = time.monotonic()

        failure = None
        retry_after = None
        try:
            response = requests.get(url,headers={"Authorization": api_key},params=params,timeout=(5,15))
        except requests.RequestException as e:












    for attempt in range(1,MAX_ATTEMPTS+1):
        if _last_request_at is None:
            sleep_time = 0.0
        else:
            sleep_time = MIN_RATE_LIMIT_SPACING_SECONDS - (time.monotonic() - _last_request_at)

        if sleep_time > 0:
            time.sleep(sleep_time)

        _last_request_at = time.monotonic()

        try:
            response = requests.get(url,headers={"Authorization": api_key},params=params,timeout=(5,15)) #tuple (5,15) is used for the time out. 5s to connect(connection time out), 15s to read (how long youll wait for the server to produce an answer)
        except request.RequestException as e:
            raise SystemExit(e)

        status_code = response.status_code

        if status_code == 401:
            raise InvalidApiKey("The API key you sent has been rejected")
        if status_code == 404:
            raise AccountNotFound(f"The account was not found, path: {path}")


        if (status_code == 429 or status_code >= 500):
            # Stops the last attempt from sleeping pointlessly.
            if attempt < MAX_ATTEMPTS:
                retry_after_response = response.headers.get("Retry-After")
                delay = retry_delay_seconds(retry_after_response,attempt)
                time.sleep(delay)
            
            continue
        
        return response.json()["data"]
    
    raise RequestFailed(f"Requests failed after the {MAX_ATTEMPTS} attempts, with status code: {status_code}")
        

def retry_delay_seconds(retry_after, attempt):
    """Returns the amount of seconds the program has to wait before moving onto its next attempt.
    
    When the retry_after is above the waiting cap it will raise a RequestFailed exception error
    """
    backoff_wait_time = BASE_BACKOFF_DELAY ** attempt
    try:
        if retry_after_seconds is None:
            return backoff_wait_time

        retry_after_seconds = int(retry_after)
        
        if retry_after_seconds <= MAX_RETRY_AFTER_SECONDS:
            return retry_after_seconds
        else: 
            raise RequestFailed(f"The retry after time response is above the {MAX_RETRY_AFTER_SECONDS} seconds cap.")
    except ValueError:
        return backoff_wait_time
    