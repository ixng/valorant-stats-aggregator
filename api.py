import time

import requests

BASE_URL = "https://api.henrikdev.xyz"
BASE_BACKOFF_DELAY = 2
MAX_ATTEMPTS = 3
MIN_RATE_LIMIT_SPACING_SECONDS = 2.0
MAX_RETRY_AFTER_SECONDS = 60.0
QUOTA_RESET_BUFFER_SECONDS = 1.0

_last_request_at = None  # monotonic time the last request was sent
_quota_remaining = None  # x-ratelimit-remaining from the most recent response
_quota_reset_at = None  # monotonic time the current quota window resets


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
    data = request(path,api_key)
    return data["puuid"]

def fetch_matches(puuid, api_key, start, size):
    path = f"valorant/v4/by-puuid/matches/eu/pc/{puuid}"
    data = request(path, api_key, params = {"size" : size, "start" : start})
    return data

def _header_int(response, name):
    """Return a header as an int, or None when it is missing or not a number."""
    value = response.headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _record_quota(response):
    """Remember what this response said about the remaining quota and when it resets.

    The API sends x-ratelimit-remaining and x-ratelimit-reset on every response, so the
    client does not have to guess how much of the window it has used.
    """
    global _quota_remaining, _quota_reset_at

    remaining = _header_int(response, "x-ratelimit-remaining")
    if remaining is not None:
        _quota_remaining = remaining

    reset = _header_int(response, "x-ratelimit-reset")
    if reset is not None:
        _quota_reset_at = time.monotonic() + reset


def wait_before_send():
    """Seconds to sleep before the next request.

    The spacing floor always applies. When the last response said the quota was spent,
    wait for the window to reset instead, since spacing alone cannot know about requests
    made by an earlier run, or by hand with the same key.
    """
    waits = [0.0]

    if _last_request_at is not None:
        waits.append(MIN_RATE_LIMIT_SPACING_SECONDS - (time.monotonic() - _last_request_at))

    if _quota_remaining == 0 and _quota_reset_at is not None:
        waits.append(_quota_reset_at - time.monotonic() + QUOTA_RESET_BUFFER_SECONDS)

    return max(waits)


def retry_delay_seconds(retry_after, attempt, reset=None):
    """Returns the amount of seconds the program has to wait before moving onto its next attempt.
    
    When the retry_after is above the waiting cap it will raise a RequestFailed exception error
    """
    for source, value in (("Retry-After", retry_after), ("x-ratelimit-reset", reset)):
        if value is None:
            continue
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            continue
        if seconds > MAX_RETRY_AFTER_SECONDS:
            raise RequestFailed(
                f"{source} asked for {seconds}s, above the {MAX_RETRY_AFTER_SECONDS}s cap"
            )
        return seconds

    return BASE_BACKOFF_DELAY ** attempt

def request(path, api_key, params=None):
    """Send a GET to the API, respecting the rate limit and retrying transient failures.
    Returns the parsed response. Raises on a permanent failure or after MAX_ATTEMPTS."""

    global _last_request_at 
    url = f"{BASE_URL}/{path}"

    for attempt in range(1, MAX_ATTEMPTS + 1):

        sleep_time = wait_before_send()
        if sleep_time > 0:
            time.sleep(sleep_time)

        _last_request_at = time.monotonic()

        failure = None # why the attempt failed; None means it succeeded
        retry_after = None  # Retry-After, when a response sends one
        reset = None  # x-ratelimit-reset, when there is a response

        try:
            response = requests.get(url,headers={"Authorization": api_key},params=params,timeout=(5,15))
        except requests.RequestException as e:
            failure = f"{type(e).__name__}: {e}"
        else:
            _record_quota(response)
            status_code = response.status_code

            if status_code == 401:
                raise InvalidApiKey("The API key you sent has been rejected")
            if status_code == 404:
                raise AccountNotFound(f"The account was not found, path: {path}")
            if status_code == 429 or status_code >= 500:
                failure = f"{status_code} ERROR"
                retry_after = response.headers.get("Retry-After")
                reset = _header_int(response, "x-ratelimit-reset")

        if failure is None:
            return response.json()["data"]
        
        if attempt == MAX_ATTEMPTS:
            raise RequestFailed(f"Requests failed after the {MAX_ATTEMPTS} attempts, caused by: {failure}")
        
        time.sleep(retry_delay_seconds(retry_after, attempt, reset))
        
                
    