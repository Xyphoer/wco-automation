import requests

class Connection:
    def __init__(self, userid, password, host):
        self.userid = userid
        self.password = password
        self.host = host
        self.current_session = self.startSession()
        self.session_token = self.current_session.json()['sessionToken']
        self.college = self.current_session.json()['payload']['roles']['operator'][1]
        self.business = self.current_session.json()['payload']['roles']['operator'][0]
        self.ebling = self.current_session.json()['payload']['roles']['operator'][3]
        self.social = self.current_session.json()['payload']['roles']['operator'][7]
        self.steenbock = self.current_session.json()['payload']['roles']['operator'][8]
        self.memorial = self.current_session.json()['payload']['roles']['operator'][6]
        self.centers = [self.college, self.business, self.ebling, self.social, self.steenbock, self.memorial]
        self.scope = self.setScope()

    def startSession(self):
        return requests.post(url = self.host + "/rest/session/start",
                        headers = {"Authorization": "Bearer Requested"},
                        json = {"userid": self.userid,
                                "password": self.password})
    
    def setScope(self):
        return requests.post(url = self.host + "/rest/session/setSessionScope",
                      headers = {"Authorization": "Bearer " + self.session_token},
                      json = {"checkoutCenter": {"_class": "checkout-center", "oid": self.college['organization']['oid']}})
    
    def getCheckouts(self, limit = 0):
        sorted_allocs = []

        for center in self.centers:
            allocs = requests.post(url = self.host + "/rest/allocation/search",
                                headers = {"Authorization": "Bearer " + self.session_token},
                                json = {"properties": ["patron", "activeTypes"], 
                                        "query": {"and": {"state": "CHECKOUT", "center": center}},
                                        #"limit": limit,
                                        "orderBy": "patronId"})
            
            sorted_allocs += list(allocs.json()['payload']['result'])

        # allocs_ltg =  requests.post(url = self.host + "/rest/allocation/search",
        #                         headers = {"Authorization": "Bearer " + self.session_token},
        #                         json = {"properties": ["patron", "activeTypes"], 
        #                                 "query": {"and": {"state": "CHECKOUT", "center": self.college}},
        #                                 #"limit": limit,
        #                                 "orderBy": "patronId"})
        
        # allocs_decom =  requests.post(url = self.host + "/rest/allocation/search",
        #                         headers = {"Authorization": "Bearer " + self.session_token},
        #                         json = {"properties": ["patron", "activeTypes"], 
        #                                 "query": {"and": {"state": "CHECKOUT", "center": self.memorial}},
        #                                 #"limit": limit,
        #                                 "orderBy": "patronId"})
        
        # sorted_allocs = list(allocs_ltg.json()['payload']['result']) + list(allocs_decom.json()['payload']['result'])
        sorted_allocs.sort(key = lambda person: person['patron']['oid'])

        return sorted_allocs
    
    def getPatron(self, patron_oid):
        return requests.post(url = self.host + "/rest/person/get",
                             headers = {"Authorization": "Bearer " + self.session_token},
                             json = {"oid": patron_oid})
    
    def close(self):
        return requests.post(url = self.host + "/rest/session/logout",
                             headers = {"Authorization": "Bearer " + self.session_token})