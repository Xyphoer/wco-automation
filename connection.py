import requests
from datetime import datetime, timedelta
from utils.Decorations import check_wco_request

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
        self.request_session = requests.Session()
        self.wco_session = self.start_session()

        # get and store session token, which will be need for authorizing requests
        self.session_token = self.wco_session.json()['sessionToken']

        # get and store checkout center information
        # Compress into just dict?
        self.college = self.wco_session.json()['payload']['roles']['operator'][1]
        self.business = self.wco_session.json()['payload']['roles']['operator'][0]
        self.ebling = self.wco_session.json()['payload']['roles']['operator'][3]
        self.social = self.wco_session.json()['payload']['roles']['operator'][7]
        self.steenbock = self.wco_session.json()['payload']['roles']['operator'][8]
        self.memorial = self.wco_session.json()['payload']['roles']['operator'][6]
        self.merit = self.wco_session.json()['payload']['roles']['operator'][5]
        self.centers = {
            "college": self.college,
            "business": self.business,
            "ebling": self.ebling,
            "socialwork": self.social,
            "steenbock": self.steenbock,
            "memorial": self.memorial,
            "merit": self.merit}

        # set the scope to LTG org to start
        self.scope = self.set_scope(self.college['organization']['oid'])

    #####
    # Name: start_session
    # Inputs: None
    # Output: Session information
    # Description: Starts the session with WCO by signing in with the provided credentials.
    #####
    @check_wco_request
    def start_session(self):
        response = self.request_session.post(url = self.host + "/rest/session/start",
                        headers = {"Authorization": "Bearer Requested"},
                        json = {"userid": self.userid,
                                "password": self.password})
        return response

    #####
    # Name: set_scope
    # Inputs: _class ("organization" or "checkout-center"), location_oid (int)
    # Output: Scope information
    # Description: Sets the scope of the session to College Library
    #####
    @check_wco_request
    def set_scope(self, location_oid: int, _class: str = "organization"):
        return self.request_session.post(url = self.host + "/rest/session/setSessionScope",
                      headers = {"Authorization": "Bearer " + self.session_token},
                      json = {"checkoutCenter": {"_class": _class, "oid": location_oid}})
    
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
            allocs = self.request_session.post(url = self.host + "/rest/allocation/search",
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

    @check_wco_request
    def get_patron_checkouts(self, patron_oid: int, properties = []):
        patron = self.get_patron(patron_oid).json()['payload']
        if properties:
            return self.request_session.post(url = self.host + "/rest/allocation/search",
                                             headers = {"Authorization": "Bearer " + self.session_token},
                                             json = {"properties": properties,
                                                     "query": {"patron": patron}})
        else:
            return self.request_session.post(url = self.host + "/rest/allocation/search",
                                             headers = {"Authorization": "Bearer " + self.session_token},
                                             json = {"query": {"patron": patron}})
    
    def get_new_overdues(self, center) -> list:
        allocs = []
        
        try:
            allocs = self.request_session.post(url = self.host + "/rest/allocation/search",
                                headers = {"Authorization": "Bearer " + self.session_token},
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
            allocs = self.request_session.post(url = self.host + "/rest/allocation/search",
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
    @check_wco_request
    def get_checkout(self, id: str):
        return self.request_session.post(url = self.host + "/rest/allocation/search",
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
            response = self.request_session.post(url = self.host + "/rest/resource/search",
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
    @check_wco_request
    def get_patron(self, patron_oid: int, properties = []):
        if properties:
            return self.request_session.post(url = self.host + "/rest/person/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": properties,
                                        "oid": patron_oid})
        else:
            return self.request_session.post(url = self.host + "/rest/person/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"oid": patron_oid})
    
    @check_wco_request
    def get_account(self, patron_oid: int):
        return self.request_session.post(url = self.host + "/rest/person/get",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"oid": patron_oid,
                                    "properties": ["defaultAccount"]})
    
    @check_wco_request
    def get_resource(self, resource_oid: int, properties = []):
        if properties:
            return self.request_session.post(url = self.host + "/rest/resource/get",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"oid": resource_oid,
                                                    "properties": properties})
        else:
            return self.request_session.post(url = self.host + "/rest/resource/get",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"oid": resource_oid})
    
    @check_wco_request
    def get_allocations(self, query: dict, properties = []):
        if properties:
            return self.request_session.post(url = self.host + "/rest/allocation/search",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"query": query,
                                                    "properties": properties})
        
        else:
            return self.request_session.post(url = self.host + "/rest/allocation/search",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"query": query})

    @check_wco_request
    def get_allocation(self, allocation_oid: int, properties = []):
        if properties:
            return self.request_session.post(url = self.host + "/rest/allocation/get",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"oid": allocation_oid,
                                                    "properties": properties})
        else:
            return self.request_session.post(url = self.host + "/rest/allocation/get",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"oid": allocation_oid})
    
    @check_wco_request
    def return_allocation(self, allocation):
        return self.request_session.post(url = self.host + "/rest/allocation/returnAllocation",
                                         headers = {"Authorization": "Bearer " + self.session_token},
                                         json = {"allocation": allocation})
    
    def delete_resource(self, resource_oid: int):
        delete_check = self.get_resource(resource_oid, ['deletable', 'deleted']).json()
        deletable, deleted = delete_check['payload']['deletable'], delete_check['payload']['deleted']

        # make more consistent return
        if deleted:
            return "already deleted"
        elif not deletable:
            return "cannot delete"
        else:
            return self.request_session.post(url = self.host + "/rest/resource/update",
                                             headers = {"Authorization": "Bearer " + self.session_token},
                                             json = {"oid": resource_oid,
                                                     "values": {"deleted": True}})
    
    @check_wco_request
    def undelete_resource(self, resource_oid: int):
        return self.request_session.post(url = self.host + "/rest/resource/update",
                                            headers = {"Authorization": "Bearer " + self.session_token},
                                            json = {"oid": resource_oid,
                                                    "values": {"deleted": False}})
    
    @check_wco_request
    def get_completed_overdue_allocations(self, start_time: datetime, end_time: datetime):
        earliest_actual_end = start_time.isoformat()
        latest_scheduled_end = (start_time - timedelta(minutes=10)).isoformat()  # 10 minute grace period
        latest_actual_end = end_time.isoformat()

        return self.request_session.post(url = self.host + "/rest/allocation/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"and": {"earliestActualEnd": earliest_actual_end, "latestScheduledEnd": latest_scheduled_end, "latestActualEnd": latest_actual_end}},
                                     "properties": ["oid", "patron", "items", "scheduledEndTime", "realEndTime", "checkoutCenter"]})
    
    # get current overdues
    @check_wco_request
    def get_current_overdue_allocations(self):
        latest_scheduled_end = (datetime.now() - timedelta(minutes=10)).isoformat()  # 10 minute grace period

        return self.request_session.post(url = self.host + "/rest/allocation/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"and": {"latestScheduledEnd": latest_scheduled_end, 'state': 'CHECKOUT'}},
                                     "properties": ["oid", "patron", "items", "scheduledEndTime", "realEndTime", "checkoutCenter", "aggregateValueOut", "uniqueId", "patronPreferredEmail", "note"]})
    
    #####
    # Name: get_open_invoices
    # Inputs: None
    # Output: Invoice information
    # Description: Get invoice information and the corresponding patrons
    #####
    @check_wco_request
    def get_open_invoices(self):
        return self.request_session.post(url = self.host + "/rest/invoice/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": {"invoiceStatus": "PENDING"},
                                     "properties": ["invoiceBalance",
                                                    "person"]})
    
    @check_wco_request
    def find_invoices(self, query: dict, properties: list = []):
        return self.request_session.post(url = self.host + "/rest/invoice/search",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"query": query,
                                     "properties": properties})
    
    @check_wco_request
    def get_invoice(self, invoice_oid: int, properties = []):
        if properties:
            return self.request_session.post(url = self.host + "/rest/invoice/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": properties,
                                        "oid": invoice_oid})
        else:
            return self.request_session.post(url = self.host + "/rest/invoice/get",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"oid": invoice_oid})
    
    @check_wco_request
    def get_invoice_lines(self, invoice):
        return self.request_session.post(url = self.host + "/rest/invoiceLine/search",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"query": {"invoice": invoice}})
    
    @check_wco_request
    def strike_invoice_line(self, invoice, line, comment = ""):
        return self.request_session.post(url = self.host + "/rest/invoice/strikeInvoiceLine",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"invoice": invoice,
                                        "line": line,
                                        "comment": comment})
    
    @check_wco_request
    def unstrike_invoice_line(self, invoice, line, comment = ""):
        return self.request_session.post(url = self.host + "/rest/invoice/unstrikeInvoiceLine",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"invoice": invoice,
                                        "line": line,
                                        "comment": comment})
    
    #####
    # Name: create_invoice
    # Inputs: account, organization, center
    # Output: Invoice information
    # Description: Create an invoice for said account, under said organization (should always be LTG),
    #              in said checkout center.
    #####
    @check_wco_request
    def create_invoice(self, account, organization, center, allocation=None, description=''):
        return self.request_session.post(url = self.host + "/rest/invoice/new",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"account": account,
                                    "organization": organization,
                                    "allocation": allocation,
                                    "checkoutCenter": center,
                                    "description": description})
    
    @check_wco_request
    def update_invoice(self, invoice_oid: int, update_dict: dict):
        return self.request_session.post(url = self.host + "/rest/invoice/update",
                                         headers = {"Authorization": "Bearer " + self.session_token},
                                         json = {'oid': invoice_oid,
                                                 'values': update_dict})
    
    @check_wco_request
    def waive_invoice(self, invoice, comment: str = '') -> requests.Response:
        return self.request_session.post(url = self.host + "/rest/invoice/waiveInvoices",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"invoices": [invoice]})
    
        # return requests.post(url = self.host + "/rest/invoice/waive",
        #                     headers = {"Authorization": "Bearer " + self.session_token},
        #                     json = {"invoice": invoice,
        #                             "comment": comment})

    @check_wco_request
    def apply_invoice_hold(self, invoice, comment: str = ''):
        return self.request_session.post(url = self.host + "/rest/invoice/applyHold",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"invoice": invoice,
                                     "comment": comment})
    
    @check_wco_request
    def remove_invoice_hold(self, invoice, comment: str = ''):
        return self.request_session.post(url = self.host + "/rest/invoice/removeHold",
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
    @check_wco_request
    def add_charge(self, invoice, amount, subtype: str, text: str = ''):
        return self.request_session.post(url = self.host + "/rest/invoice/addCharge",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"amount": amount,
                                    "invoice": invoice,
                                    "subtype": subtype,
                                    "text": text})
    
    @check_wco_request
    def add_invoice_note(self, invoice, text: str):
        return self.request_session.post(url = self.host + "/rest/invoice/addNote",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"invoice": invoice,
                                    "text": text})
    
    @check_wco_request
    def email_invoice(self, invoice):
        return self.request_session.post(url = self.host + "/rest/invoice/emailInvoice",
                            headers = {"Authorization": "Bearer " + self.session_token},
                            json = {"invoice": invoice})
    
    #####
    # Name: close
    # Inputs: none
    # Output: Logout information
    # Description: Logout of the WCO session
    #####
    @check_wco_request
    def close(self):
        return self.request_session.post(url = self.host + "/rest/session/logout",
                             headers = {"Authorization": "Bearer " + self.session_token})