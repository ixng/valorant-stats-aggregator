import requests


BASE_URL = "https://api.henrikdev.xyz"

#Call the account endpoint and return the PUUID.
def fetch_account(name, tag, api_key):
    url = f"{BASE_URL}/valorant/v2/account/{name}/{tag}"
    response = requests.get(url,headers={"Authorization":api_key})
    status_code = response.status_code

    #404: The riot id does not exist. 401: The server does not know who you are ie the api key is not recognised
    if status_code == 404:
        raise ValueError(f"The riot id you are looking for doesn't exist. RIOT_ID: {name}#{tag}")
    if status_code == 401:
        raise ValueError("The API key you requested has been rejected")

    #To handle all other errors that aren't to do with the api key and the riot id provided
    if status_code != 200:
        raise ValueError(f"Unexpected error. Status code: {status_code}")
    
    data = response.json()["data"]
    
    return data["puuid"]

