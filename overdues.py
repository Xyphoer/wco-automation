from connection import Connection
from postgres import Postgres
from datetime import datetime, timedelta
from utils import utils

class Overdues:

    def __init__(self, connection: Connection, utilities: utils, db):
        self.connection = connection
        self.utils = utilities
        self.db = db
    
    ## can handle returned items. Need handler for placing holds and fines
    def update(self, start_time: str, end_time: str) -> dict:
        # update db with new overdue items for patrons (Note: only count if the checkout is completed)
        # returns dictionary of changes
        start_time = datetime.strptime(start_time, '%m/%d/%Y')
        end_time = datetime.strptime(end_time, '%m/%d/%Y')
        insert_dict = {}
        insert_query = ''

        response = self.connection.get_completed_overdue_allocations(start_time, end_time)

        for allocation in response.json()['payload']['result']:
            
            conseq, end_time, checkout_center = self.utils.get_overdue_consequence(allocation)
            # add initial stop date (to not count past when we start)

            ### Set hold end time to start counting from once replacement fee is paid (if applicable)

            try:
                insert_dict[allocation['patron']['oid']][0] += allocation['itemCount']
                insert_dict[allocation['patron']['oid']][1:] = ['True' if conseq['Hold'] else 'False',  # hold_status
                                                                'True' if conseq['Fee'] else 'False',   # fee_status
                                                                conseq['Hold'],                         # hold_length
                                                                f"'{end_time + timedelta(days=conseq['Hold'])}'" if conseq['Hold'] else 'NULL', # hold_remove_time
                                                                checkout_center]    # checkout center for hold

            except KeyError as e:
                insert_dict[allocation['patron']['oid']] = [allocation['itemCount'],
                                                            'True' if conseq['Hold'] else 'False',  # hold_status
                                                            'True' if conseq['Fee'] else 'False',   # fee_status
                                                            conseq['Hold'],                         # hold_length
                                                            f"'{end_time + timedelta(days=conseq['Hold'])}'" if conseq['Hold'] else 'NULL', # hold_remove_time
                                                            checkout_center]    # checkout center for hold

        for key, value in insert_dict.items():
            if value[2] == 'True': value[4] = 'NULL'

            #if value[1] == 'True': self.place_hold(key, end=value[4], checkout_center=value[5], message="")

            insert_query += f"({key}, {value[0]}, {value[1]}, {value[2]}, {value[3]}, {value[4]}),\n" 
        
        self.db.run("INSERT INTO " \
                        "overdues (patron_oid, count, hold_status, fee_status, hold_length, hold_remove_time) " \
                    "VALUES " \
                        f"{insert_query.strip()[:-1]}" \
                    "ON CONFLICT (patron_oid) DO " \
                        "UPDATE SET count = overdues.count + EXCLUDED.count, " \
                        "hold_status = overdues.hold_status OR EXCLUDED.hold_status, " \
                        "fee_status = overdues.fee_status OR EXCLUDED.fee_status, " \
                        "hold_remove_time = CASE " \
                            "WHEN overdues.fee_status OR EXCLUDED.fee_status " \
                                "THEN NULL " \
                            "WHEN overdues.count = 5 " \
                                f"THEN '{end_time + timedelta(days=90)}' " \
                            "WHEN overdues.count = 10 " \
                                f"THEN '{end_time + timedelta(days=180)}' " \
                            "WHEN overdues.count > 11 " \
                                f"THEN NULL " \
                            "WHEN overdues.hold_remove_time < EXCLUDED.hold_remove_time " \
                                "THEN EXCLUDED.hold_remove_time " \
                            "WHEN overdues.hold_remove_time IS NOT NULL " \
                                "THEN overdues.hold_remove_time " \
                            "ELSE EXCLUDED.hold_remove_time " \
                        "END")
    
    def get_patrons(self, oid: list = [], name: list = [], wiscard: list = []) -> list:
        # get patrons from database
        pass

    def reduce_overdue_count(self, oid: int = None, name: str = None, wiscard: int = None, amount: int = 0) -> tuple:
        # reduce a patron overdue item count by amount. Returnes a tuple of (before_count, after_count)
        pass

    def increase_overdue_count(self, oid: int = None, name: str = None, wiscard: int = None, amount: int = 0) -> tuple:
        # incease a patron overdue item count by amount. Returnes a tuple of (before_count, after_count)
        pass

    def place_hold(self, oid: int, end, checkout_center, message):
        account = self.connection.get_account(oid).json()
        invoice = self.connection.create_invoice(account['payload']['defaultAccount'], account['session']['organization'], checkout_center).json()
        hold = self.connection.apply_invoice_hold(invoice['payload'], message)

        self.db.run(f"UPDATE overdues SET hold_status = True, hold_remove_time = '{end}' WHERE patron_oid = {oid}")

    #def remove_hold(self)

wco_host = ''
wco_userid = ''
wco_password = ''
redmine_host = ''
redmine_session_cookie = ''
redmine_auth_key = ''
shibsession_cookie_name = ''
shibsession_cookie_value = ''
postgres_pass = ''

try:
    with open('config.txt', 'r', encoding='utf-8') as in_file:
        for line in in_file:
            if "wco_host" in line.lower():
                wco_host = line.split("=")[1].strip()
            elif "wco_user_id" in line.lower():
                wco_userid = line.split("=")[1].strip()
            elif "wco_password" in line.lower():
                wco_password = line.split("=")[1].strip()
            elif "redmine_host" in line.lower():
                redmine_host = line.split("=")[1].strip()
            elif "redmine_session_cookie" in line.lower():
                redmine_session_cookie = line.split("=")[1].strip()
            elif "shibsession_cookie_name" in line.lower():
                shibsession_cookie_name = line.split("=")[1].strip()
            elif "shibsession_cookie_value" in line.lower():
                shibsession_cookie_value = line.split("=")[1].strip()
            elif "redmine_auth_key" in line.lower():
                redmine_auth_key = line.split("=")[1].strip()
            elif "postgres" in line.lower():
                postgres_pass = line.split("=")[1].strip()

                
except OSError as e:
        wco_host = input("WebCheckout host: ")
        wco_userid = input("WebCheckout user id: ")
        wco_password = input("WebCheckout Password: ")
        redmine_host = input("Redmine host: ")
        redmine_session_cookie = input("redmine_session_cookie: ")
        shibsession_cookie_name = input("_shibsession cookie name: ")
        shibsession_cookie_value = input("_shibsession cookie value: ")

db = Postgres(f"dbname=postgres user=postgres password={postgres_pass}")

db.run("CREATE TABLE IF NOT EXISTS overdues (patron_oid INTEGER PRIMARY KEY, count INTEGER, hold_status BOOLEAN DEFAULT FALSE, fee_status BOOLEAN DEFAULT FALSE, hold_length INTEGER, hold_remove_time TIMESTAMP)")

wco_conn = Connection(wco_userid, wco_password, wco_host)
oconn = Overdues(wco_conn, utils(wco_conn), db)

oconn.update('11/15/2023', '11/21/2023')
