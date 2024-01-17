import requests
from datetime import datetime, timedelta

#####
# Name: Connection
# Inputs: userid (string), password (string), host (string)
# Description: Manage connection to WebCheckout, including put and get requests and session information.
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
        # Compress into just dict?
        self.college = self.current_session.json()['payload']['roles']['operator'][1]
        self.business = self.current_session.json()['payload']['roles']['operator'][0]
        self.ebling = self.current_session.json()['payload']['roles']['operator'][3]
        self.social = self.current_session.json()['payload']['roles']['operator'][7]
        self.steenbock = self.current_session.json()['payload']['roles']['operator'][8]
        self.memorial = self.current_session.json()['payload']['roles']['operator'][6]
        self.merit = self.current_session.json()['payload']['roles']['operator'][5]
        self.centers = {
            "college": self.college,
            "business": self.business,
            "ebling": self.ebling,
            "social": self.social,
            "steenbock": self.steenbock,
            "memorial": self.memorial,
            "merit": self.merit}

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
    # Description: Gets and sorts all allocations (checkouts) by oid. Contains active types and patron information only.
    #              Likely to be combined with get_checkouts_for_overdue later.
    #####
    def get_checkouts(self, limit = 0) -> list:
        # to hold all checkouts
        sorted_allocs = []

        # get checkouts for every location
        for center in self.centers:
            allocs = requests.post(url = self.host + "/rest/allocation/search",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": ["patron", "activeTypes", "checkoutCenter"], 
                                        "query": {"and": {"state": "CHECKOUT", "center": center}},
                                        #"limit": limit,
                                        "orderBy": "patronId"})
            
            # store this locations checkouts in sorted_allocs
            sorted_allocs += list(allocs.json()['payload']['result'])

        # sort the allocations by oid
        sorted_allocs.sort(key = lambda person: person['patron']['oid'])

        return sorted_allocs
    
    def get_new_overdues(self, center) -> list:
        allocs = []
        
        try:
            allocs = requests.post(url = self.host + "/rest/allocation/search",
                                headers = {"authorization": "Bearer " + self.session_token},
                                json = {"properties": ["uniqueId", "patron", "patronPreferredEmail", "scheduledEndTime", "note", "itemNames"],
                                        "query": {"and": {"state": "CHECKOUT", "center": self.centers[center]}},
                                        "orderBy": "patronId"})
        
        except IndexError as e:
            pass # Log error
        
        return allocs
    
    #####
    # Name: get_checkouts_for_overdue
    # Inputs: None
    # Output: sorted_allocs (dict)
    # Description: Gets and sorts all allocations (checkouts) by center. Contains unique id (CK-####), patron information,
    #              start time, scheduled end time, and item names.
    #              Likely to be merged into get_checkouts later.
    #####
    def get_checkouts_for_overdue(self):
        sorted_allocs = {}  # to hold dictionary of checkouts by location

        for center in self.centers:
            # get checkout information from each location
            allocs = requests.post(url = self.host + "/rest/allocation/search",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": ["uniqueId", "patron", "realStartTime", "scheduledEndTime", "itemNames"], 
                                        "query": {"and": {"state": "CHECKOUT", "center": center}},
                                        "orderBy": "patronId"})
            
            # add checkouts to center information
            sorted_allocs[center['name']] = list(allocs.json()['payload']['result'])

        return sorted_allocs
    
    #####
    # Name: get_checkout
    # Inputs: id (str)
    # Output: checkout information
    # Description: Gets a specific checkout by it's unique CK-#### id
    #####
    def get_checkout(self, id: str):
        return requests.post(url = self.host + "/rest/allocation/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"uniqueId": id}})
    
    #####
    # Name: get_items_by_serial
    # Inputs: serial (list)
    # Output: resource information
    # Description: Gets the CK-### id, oid, and item name for each item of a list of items by serial number
    #####
    def get_items_by_serial(self, serial: list):
        for number in serial:
            response = requests.post(url = self.host + "/rest/resource/search",
                        headers = {"Authorization": "Bearer " + self.session_token},
                        json = {"properties": ["uniqueId", "oid", "statusString"],
                        "query": {"serialNumber": number}})
            yield(response)
    
    #####
    # Name: get_patron
    # Inputs: patron_oid (string)
    # Output: Patron information
    # Description: Get patron information using their oid
    #####
    def get_patron(self, patron_oid: int, properties = []):
        if properties:
            return requests.post(url = self.host + "/rest/person/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": properties,
                                        "oid": patron_oid})
        else:
            return requests.post(url = self.host + "/rest/person/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"oid": patron_oid})
    
    def get_account(self, patron_oid: int):
        return requests.post(url = self.host + "/rest/person/get",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"oid": patron_oid,
                                    "properties": ["defaultAccount"]})
    
    def get_completed_overdue_allocations(self, start_time: datetime, end_time: datetime):
        earliest_actual_end = start_time.isoformat()
        latest_scheduled_end = (start_time - timedelta(minutes=10)).isoformat()  # 10 minute grace period
        latest_actual_end = end_time.isoformat()

        return requests.post(url = self.host + "/rest/allocation/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"and": {"earliestActualEnd": earliest_actual_end, "latestScheduledEnd": latest_scheduled_end, "latestActualEnd": latest_actual_end}},
                                     "properties": ["oid", "patron", "itemCount", "allTypes", "scheduledEndTime", "realEndTime", "checkoutCenter"]})
    
    # get current overdues
    def get_current_overdue_allocations(self):
        latest_scheduled_end = (datetime.now() - timedelta(minutes=10)).isoformat()  # 10 minute grace period

        return requests.post(url = self.host + "/rest/allocation/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"and": {"latestScheduledEnd": latest_scheduled_end, 'state': 'CHECKOUT'}},
                                     "properties": ["oid", "patron", "itemCount", "allTypes", "scheduledEndTime", "realEndTime", "checkoutCenter", "aggregateValueOut"]})
    
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
                                                    "person"]})
    
    def find_invoices(self, query: dict, properties: list = []):
        return requests.post(url = self.host + "/rest/invoice/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": query,
                                     "properties": properties})
    
    def get_invoice(self, invoice_oid: int, properties = []):
        if properties:
            return requests.post(url = self.host + "/rest/invoice/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": properties,
                                        "oid": invoice_oid})
        else:
            return requests.post(url = self.host + "/rest/invoice/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"oid": invoice_oid})
    
    #####
    # Name: create_invoice
    # Inputs: account, organization, center
    # Output: Invoice information
    # Description: Create an invoice for said account, under said organization (should always be LTG),
    #              in said checkout center.
    #####
    def create_invoice(self, account, organization, center, allocation=None):
        return requests.post(url = self.host + "/rest/invoice/new",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"account": account,
                                    "organization": organization,
                                    "allocation": allocation,
                                    "checkoutCenter": center})
    
    def waive_invoice(self, invoice, comment: str = '') -> requests.Response:
        return requests.post(url = self.host + "/rest/invoice/waive",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"invoices": invoice,
                                    "comment": comment})

    def apply_invoice_hold(self, invoice, comment: str = ''):
        return requests.post(url = self.host + "/rest/invoice/applyHold",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"invoice": invoice,
                                     "comment": comment})
    
    def remove_invoice_hold(self, invoice, comment: str = ''):
        return requests.post(url = self.host + "/rest/invoice/removeHold",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"invoice": invoice,
                                     "comment": comment})
    
    #####
    # Name: add_charge
    # Inputs: invoice, amount (str), subtype (str)
    # Output: Invoice information
    # Description: Add a charge to an invoice. Requires amount, desired invoice, and subtype.
    #              Subtype must be one of "Abuse Fine", "Late Fine", "Loss", "Damage", "Usage Fee", "Supplies",
    #              "Overtime", "Labor", "Shipping", or "Other."
    #####
    def add_charge(self, invoice, amount: str, subtype: str):
        return requests.post(url = self.host + "/rest/invoice/addCharge",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"amount": amount,
                                    "invoice": invoice,
                                    "subtype": subtype})
    
    #####
    # Name: close
    # Inputs: none
    # Output: Logout information
    # Description: Logout of the WCO session
    #####
    def close(self):
        return requests.post(url = self.host + "/rest/session/logout",
                             headers = {"Authorization": "Bearer " + self.session_token})