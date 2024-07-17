import requests
import logging

module_logger = logging.getLogger(__name__)

# decorator to format wco_responses,
# check for expected and unexcpected errors
# passing on the unexcpected errors after logging,
# and raise custom errors when wco fails to provide
def check_wco_request(func):

    def wrapper(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
        except requests.exceptions.ConnectionError as e:
            module_logger.debug(f'ConnectionError in {func.__name__} | request body: {response.request.body}')
            module_logger.exception(e)
            raise

        ## Temporarily ignoring special cases
        if type(response) != requests.Response:
            return response
        ##

        # check response is good
        # it is the job of functions using the wco_request function to cleanly save state and exit from errors such as this
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            module_logger.debug(f'HTTP {e.response.status_code} in {func.__name__} | request body: {response.request.body}')
            if not (e.response.status_code == 500 and 'removeHold' in e.response.url):
                module_logger.exception(e)
                raise
            else:
                module_logger.info(f'Suspected hold already removed')
                module_logger.debug(e)

        # check response is good again since WCO returns HTTP 200 whenever possible
        data = response.json()

        # check empty payload
        if data['payload'] == None:
            err = requests.exceptions.HTTPError('404 - No Payload - Manually Thrown')
            module_logger.debug(f'Empty WebCheckout payload in {func.__name__} | request url: {response.url} | request body: {response.request.body}')
            module_logger.exception(err)
            raise(err)
        elif data['status'].lower() == 'unauthenticated':
            err = requests.exceptions.HTTPError(f'401 - Unauthorized - {data["payload"]} - Manually Thrown')
            module_logger.debug(f'Unauthenticated WebCheckout request in {func.__name__} | request url: {response.url} | request body: {response.request.body}')
            module_logger.exception(err)
            raise(err)
        elif data['status'].lower() == 'error':
            err = requests.exceptions.HTTPError(f'400 - Bad Request - {data["payload"]} - Manually Thrown')
            module_logger.debug(f'Bad WebCheckout request in {func.__name__} | request url: {response.url} | request body: {response.request.body}')
            module_logger.exception(err)
            raise(err)

        ### continue with wco formatted checking
        return data
    
    return wrapper

def check_request(func):

    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)
        # check response is good
        # it is the job of functions using the wco_request function to cleanly save state and exit from errors such as this
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            module_logger.debug(f'Bad request in {func.__name__} | request body: {response.request.body}')
            module_logger.exception(e)
        data = response.json()
        return data

    return wrapper