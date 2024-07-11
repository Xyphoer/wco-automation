import requests

def check_wco_request(func):

    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)

        ## Temporarily ignoring special cases
        if type(response) != requests.Response:
            return response
        ##

        # check response is good
        # it is the job of functions using the wco_request function to cleanly save state and exit from errors such as this
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if not(e.response.status_code == 500 and 'removeHold' in e.response.url):
                raise(e)

        # check response is good again since WCO returns HTTP 200 whenever possible
        data = response.json()
        ### continue with wco formatted checking
        return data
    
    return wrapper

def check_request(func):

    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)
        # check response is good
        # it is the job of functions using the wco_request function to cleanly save state and exit from errors such as this
        response.raise_for_status()
        data = response.json()
        return data

    return wrapper