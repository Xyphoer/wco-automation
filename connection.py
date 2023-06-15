import requests

#####
# Name: Connection
# Inputs: userid (string), password (string), host (string)
# Description: Manage connection to WebCheckout, including post and get requests and session information.
#####
class Connection:
    def __init__(self, userid: str, password: str, host: str):
        # store login info and the connection location (WCO)
        self.userid = userid
        self.password = password
        self.host = host

        # create session
        self.current_session = self.start_session()

        # get and store session token, which will be need for authorizing requests
        self.session_token = self.current_session.json()['sessionToken']

        # get and store checkout center information
        self.college = self.current_session.json()['payload']['roles']['operator'][1]
        self.business = self.current_session.json()['payload']['roles']['operator'][0]
        self.ebling = self.current_session.json()['payload']['roles']['operator'][3]
        self.social = self.current_session.json()['payload']['roles']['operator'][7]
        self.steenbock = self.current_session.json()['payload']['roles']['operator'][8]
        self.memorial = self.current_session.json()['payload']['roles']['operator'][6]
        self.merit = self.current_session.json()['payload']['roles']['operator'][5]
        self.centers = [self.college, self.business, self.ebling, self.social, self.steenbock, self.memorial, self.merit]

        # set the scope to College to start
        self.scope = self.set_scope()

    #####
    # Name: start_session
    # Inputs: None
    # Output: Session information
    # Description: Starts the session with WCO by signing in with the provided credentials.
    #####
    def start_session(self):
        return requests.post(url = self.host + "/rest/session/start",
                        headers = {"Authorization": "Bearer Requested"},
                        json = {"userid": self.userid,
                                "password": self.password})
    #####
    # Name: set_scope
    # Inputs: None
    # Output: Scope information
    # Description: Sets the scope of the session to College Library
    #####
    def set_scope(self):
        return requests.post(url = self.host + "/rest/session/setSessionScope",
                      headers = {"Authorization": "Bearer " + self.session_token},
                      json = {"checkoutCenter": {"_class": "checkout-center", "oid": self.college['organization']['oid']}})
    
    #####
    # Name: get_checkouts
    # Inputs: limit (integer)
    # Output: sorted_allocs (list)
    # Description: Gets and sorts all allocations (checkouts) by oid
    #####
    def get_checkouts(self, limit = 0) -> list:
        # to hold all checkouts
        sorted_allocs = []

        # get checkouts for every location
        for center in self.centers:
            allocs = requests.post(url = self.host + "/rest/allocation/search",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": ["patron", "activeTypes"], 
                                        "query": {"and": {"state": "CHECKOUT", "center": center}},
                                        #"limit": limit,
                                        "orderBy": "patronId"})
            
            # store this locations checkouts in sorted_allocs
            sorted_allocs += list(allocs.json()['payload']['result'])

        # sort the allocations by oid
        sorted_allocs.sort(key = lambda person: person['patron']['oid'])

        return sorted_allocs
    
    #####
    # Name: get_patron
    # Inputs: patron_oid (string)
    # Output: Patron information
    # Description: Get patron information using their oid
    #####
    def get_patron(self, patron_oid: str):
        return requests.post(url = self.host + "/rest/person/get",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"oid": patron_oid})
    
    #####
    # Name: get_open_invoices
    # Inputs: None
    # Output: Invoice information
    # Description: Get invoice information and the corresponding patrons
    #####
    def get_open_invoices(self):
        return requests.post(url = self.host + "/rest/invoice/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"invoiceStatus": "PENDING"},
                                     "properties": ["invoiceBalance",
                                                    "patron"]})
    
    #####
    # Name: close
    # Inputs: none
    # Output: Logout information
    # Description: Logout of the WCO session
    #####
    def close(self):
        return requests.post(url = self.host + "/rest/session/logout",
                             headers = {"Authorization": "Bearer " + self.session_token})