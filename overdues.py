from connection import Connection
from postgres import Postgres
from datetime import datetime, timedelta, timezone
from utils import utils, Repercussions

class Overdues:

    def __init__(self, connection: Connection, utilities: utils, db):
        self.connection = connection
        self.utils = utilities
        self.db = db
    
    ## can handle returned items and holds. Need fines still
    def update(self, start_time: str, end_time: str = '') -> dict:
        self._process_returned_overdues(start_time, end_time)
        self._process_fines()
        self._remove_holds()
        self._process_current_overdues()
    
    def get_patrons(self, oid: list = [], name: list = [], wiscard: list = []) -> list:
        # get patrons from database
        pass

    def reduce_overdue_count(self, oid: int = None, name: str = None, wiscard: int = None, amount: int = 0) -> tuple:
        # reduce a patron overdue item count by amount. Returnes a tuple of (before_count, after_count)
        pass

    def increase_overdue_count(self, oid: int = None, name: str = None, wiscard: int = None, amount: int = 0) -> tuple:
        # incease a patron overdue item count by amount. Returnes a tuple of (before_count, after_count)
        pass

    # (Turn into place_invoice and have hold & fine?) place hold and update db. NOTE: Done -- This does not update overdue count, just the hold status.
    # automatically sends an email based on WCO settins
    def place_hold(self, oid: int, checkout_center, allocation = None, end = None, message = '', update_db = True):
        account = self.connection.get_account(oid).json()
        invoice = self.connection.create_invoice(account['payload']['defaultAccount'], account['session']['organization'], checkout_center, allocation=allocation,
                                                 description="Invoice for violation of overdue policies: https://kb.wisc.edu/infolabs/131963").json()
        _hold = self.connection.apply_invoice_hold(invoice['payload'], message)
        invoice_oid = invoice['payload']['oid']

        if update_db:
            hold_length = end - datetime.now() if end else 'NULL'

            if end:
                self.db.run("INSERT INTO " \
                                "overdues (patron_oid, hold_status, hold_length, hold_remove_time, invoice_oid)" \
                            "VALUES " \
                                f"({oid}, True, {hold_length}, {end}, {invoice_oid})" \
                            "ON CONFLICT (patron_oid) DO " \
                                f"UPDATE SET hold_status = True, hold_length = {hold_length}, hold_remove_time = {end}, invoice_oid = {invoice_oid}")
            else:
                self.db.run("INSERT INTO " \
                                "overdues (patron_oid, hold_status, invoice_oid)" \
                            "VALUES " \
                                f"({oid}, True, {invoice_oid})" \
                            "ON CONFLICT (patron_oid) DO " \
                                f"UPDATE SET hold_status = True, invoice_oid = {invoice_oid}")
        
        return invoice['payload']

    # remove a specific hold
    def remove_hold(self, invoice_oid: int):
        invoice = self.connection.get_invoice(invoice_oid).json()['payload']
        self.connection.remove_invoice_hold(invoice)  # NOTE: Works, but WCO thows 500 error if hold already gone
        self.connection.waive_invoice(invoice)
        return

    def place_fee(self, invoice_oid, cost: int):

        invoice = self.connection.get_invoice(invoice_oid).json()['payload']
        self.connection.add_charge(invoice, amount=cost, subtype="Loss")
        self.connection.email_invoice(invoice)

        self.db.run("UPDATE overdues " \
                    f"SET fee_status = {True} " \
                    f"WHERE invoice_oid = {invoice_oid}")

        return invoice
    
    # get all current overdues and apply holds (if >1day or reserve) and update DB -- DONE: NEED TEST
    def _process_current_overdues(self):
        response = self.connection.get_current_overdue_allocations()

        current_holds = self.db.all('SELECT patron_oid FROM overdues WHERE hold_status')
        current_fines = self.db.all('SELECT patron_oid FROM overdues WHERE fee_status')
        excluded_checkouts = self.db.all('SELECT allocation_oid FROM excluded_allocations')

        for allocation in response.json()['payload']['result']:

            if allocation['oid'] not in excluded_checkouts:
                center = allocation['checkoutCenter']
                patron_oid = allocation['patron']['oid']

                scheduled_end = datetime.strptime(allocation['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
                tz = timezone(timedelta(hours=-6), name='utc-6')
                #tz.dst = True
                policy_start_date = datetime(year=2024, month=1, day=23, tzinfo=tz)
                if scheduled_end < policy_start_date:
                    scheduled_end = policy_start_date
                overdue_length = (datetime.now(tz=tz) - scheduled_end).days

                allocation_types = [item['rtype'] for item in allocation['items'] if item['action'].lower() == 'checkout']
                consequences = Repercussions(overdue_length, allocation_types).update()

                if consequences['Hold']:
                    if patron_oid not in current_holds and allocation['oid'] not in excluded_checkouts:  # only processing one checkout at a time
                        invoice_oid = self.place_hold(patron_oid, center)['oid']
                    else:
                        invoice_oid = self.db.one(f'SELECT invoice_oid FROM overdues WHERE patron_oid={patron_oid}')
                        if allocation['oid'] in excluded_checkouts:
                            self.remove_hold(invoice_oid)
                            if consequences['Registrar Hold']:
                                person = self.connection.get_patron(patron_oid, ['barcode']).json()['payload']
                                print(f'Excluded Registrar Hold Patron - Remove: {person["name"]} - ({person["barcode"]})')
                            continue
                    if consequences['Fee']:
                        if patron_oid not in current_fines:  # only processing one checkout at a time
                            charge = allocation['aggregateValueOut'] if allocation['aggregateValueOut'] else 2000
                            self.place_fee(invoice_oid, charge)
                        if consequences['Registrar Hold']:
                            person = self.connection.get_patron(patron_oid, ['barcode']).json()['payload']
                            print(f'Registrar Hold needed for: {person["name"]} - ({person["barcode"]})')
        return

    # get all returned overdues and resolve hold end date, fine, or fully create if needed. -- NOTE: Need fine implement & alloc with diff return times handler
    def _process_returned_overdues(self, start_search_time: str, end_search_time: str = ''): #  -> dict
        # update db with new overdue items for patrons (Note: only count if the checkout is completed)
        # update step: returns dictionary of changes
        start_search_time = datetime.strptime(start_search_time, '%m/%d/%Y')
        end_search_time = datetime.strptime(end_search_time, '%m/%d/%Y') if end_search_time else datetime.now()
        insert_dict = {}
        insert_query = ''

        current_holds = self.db.all('SELECT patron_oid FROM overdues WHERE hold_status')
        current_fines = self.db.all('SELECT patron_oid, invoice_oid FROM overdues WHERE fee_status')
        excluded_checkouts = self.db.all('SELECT allocation_oid FROM excluded_allocations')

        response = self.connection.get_completed_overdue_allocations(start_search_time, end_search_time)

        for allocation in response.json()['payload']['result']:
            if allocation['oid'] not in excluded_checkouts:
                conseq, end_time, checkout_center = self.utils.get_overdue_consequence(allocation)

                # If they have a fine, remove it as they returned the item
                for entry in current_fines:
                    if allocation['patron']['oid'] == entry[0]:
                        struck = False
                        invoice = self.connection.get_invoice(entry[1]).json()['payload']
                        invoice_lines = self.connection.get_invoice_lines(invoice).json()['payload']['result']
                        for invoice_line in invoice_lines:
                            if invoice_line['type'] == 'CHARGE' and not invoice_line['struck']:
                                self.connection.strike_invoice_line(invoice, invoice_line)  # APPLY HOLD AGAIN, PAYING REMOVES IT
                                struck = True
                        if struck:
                            self.connection.apply_invoice_hold(invoice)
                        if conseq['Registrar Hold']:
                            # name = self.connection.get_patron(allocation['patron']['oid'], ['name']).json()['payload']['name']
                            print(f"Items returned, registrar hold can be removed for oid: {allocation['patron']['oid']} -- {allocation['patron']['name']}")

                # handle partial returns before due date
                item_count = 0
                for item in allocation['items']:
                    item_returned = datetime.strptime(item['realReturnTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    allocation_due = datetime.strptime(item['returnTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    if item_returned > allocation_due + timedelta(minutes=10):
                        item_count += 1

                try:
                    insert_dict[allocation['patron']['oid']][0] += item_count
                    insert_dict[allocation['patron']['oid']][1:] = ['True' if conseq['Hold'] else 'False',  # hold_status
                                                                    'False',                                # fee_status ALWAYS false for returned items
                                                                    conseq['Hold'],                         # hold_length
                                                                    f"'{end_time + timedelta(days=conseq['Hold'])}'" if conseq['Hold'] else 'NULL', # hold_remove_time
                                                                    checkout_center]    # checkout center for hold

                except KeyError as e:
                    insert_dict[allocation['patron']['oid']] = [item_count,
                                                                'True' if conseq['Hold'] else 'False',  # hold_status
                                                                'False',                                # fee_status ALWAYS false for returned items
                                                                conseq['Hold'],                         # hold_length
                                                                f"'{end_time + timedelta(days=conseq['Hold'])}'" if conseq['Hold'] else 'NULL', # hold_remove_time
                                                                checkout_center]    # checkout center for hold

        for key, value in insert_dict.items():
            invoice_oid = False

            if key not in current_holds:
                if value[1] == 'True':
                    invoice = self.place_hold(key, checkout_center=value[5], update_db=False)
                    invoice_oid = invoice['oid']

            insert_query += f"({key}, {value[0]}, {value[1]}, {value[2]}, {value[3]}, {value[4]}, {invoice_oid if invoice_oid else 'NULL'}),\n" 
        

        # "WHEN overdues.fee_status OR EXCLUDED.fee_status " \
        #                         "THEN NULL " \
            # fee_status = overdues.fee_status OR EXCLUDED.fee_status
        if insert_query:
            self.db.run("INSERT INTO " \
                            f"overdues (patron_oid, count, hold_status, fee_status, hold_length, hold_remove_time, invoice_oid) " \
                        "VALUES " \
                            f"{insert_query.strip()[:-1]}" \
                        "ON CONFLICT (patron_oid) DO " \
                            "UPDATE SET count = overdues.count + EXCLUDED.count, " \
                            "hold_status = overdues.hold_status OR EXCLUDED.hold_status, " \
                            "fee_status = EXCLUDED.fee_status, " \
                            "hold_remove_time = CASE " \
                                "WHEN overdues.count = 5 " \
                                    f"THEN (EXCLUDED.hold_remove_time - (EXCLUDED.hold_length || ' days')::INTERVAL + '90 days'::INTERVAL)::TIMESTAMP " \
                                "WHEN overdues.count = 10 " \
                                    f"THEN (EXCLUDED.hold_remove_time - (EXCLUDED.hold_length || ' days')::INTERVAL + '180 days'::INTERVAL)::TIMESTAMP " \
                                "WHEN overdues.count > 11 " \
                                    f"THEN NULL " \
                                "WHEN overdues.hold_remove_time < EXCLUDED.hold_remove_time " \
                                    "THEN EXCLUDED.hold_remove_time " \
                                "WHEN overdues.hold_remove_time IS NOT NULL " \
                                    "THEN overdues.hold_remove_time " \
                                "ELSE EXCLUDED.hold_remove_time " \
                            "END, " \
                            "invoice_oid = CASE " \
                                "WHEN EXCLUDED.invoice_oid IS NOT NULL " \
                                    "THEN EXCLUDED.invoice_oid " \
                                "WHEN overdues.invoice_oid IS NOT NULL " \
                                    "THEN overdues.invoice_oid " \
                                "ELSE NULL " \
                            "END")
        
        return

    # check for those who have paid their fine, and resolve hold end date if they have NOTE: Done   ALSO: return and delete (paying fine equates to lost) NOTE: Done, UPGRADE PATH
    # NOTE: still open $0.00 holds count as 'Paid' not 'Pending' thus are not open. (Still can have hold). Staff can 'strike' charges when they are paid.
    def _process_fines(self):
        fined_patrons = self.db.all('SELECT patron_oid, hold_length, invoice_oid FROM overdues WHERE fee_status')
        db_update = []

        for patron_oid, hold_length, invoice_oid in fined_patrons:
            invoice = self.connection.get_invoice(invoice_oid, ['datePaid', 'isHold']).json()['payload']
            if invoice['datePaid']:

                name = self.connection.get_patron(patron_oid, ['name']).json()['payload']['name']
                print(f"Patron oid: {patron_oid} -- paid fine -- {name} -- Return & Delete item")

                date_paid = datetime.strptime(invoice['datePaid'], '%Y-%m-%dT%H:%M:%S.%f%z')
                db_update.append((patron_oid, date_paid + timedelta(days=hold_length)))   # NOTE: if fine on second overdue of overlapping, uses first length. NOT IDEAL (fallback anything though - all paid fines should be returned)
            # if not invoice['isHold']: # decide methodology (place_hold creates invoice... Seperate functions? or just hold stuff here) -- Note: Should not come into play, backup for if staff removes hold. Update path.
        
        if db_update:   # NOTE: if has current overdue time does not preserve/take greatest, overwrites.
            self.db.run(f"UPDATE overdues SET " \
                            "hold_remove_time = batch.hold_remove_time " \
                        f"FROM (VALUES ({', '.join(db_update)})) AS batch(patron_oid, hold_remove_time) " \
                        "WHERE overdues.patron_oid = batch.patron_oid")

    # remove holds on patrons who have reached the designated time of removal. DONE
    def _remove_holds(self):
        now = datetime.now()
        holds_removed = []

        potential_holds = self.db.all('SELECT patron_oid, hold_remove_time, invoice_oid FROM overdues WHERE hold_status')

        for patron_oid, hold_remove_time, invoice_oid in potential_holds:
            if hold_remove_time and hold_remove_time < now:
                self.remove_hold(invoice_oid)
                holds_removed.append(f"({patron_oid})")
        if holds_removed:
            self.db.run(f"UPDATE overdues SET " \
                        f"hold_status = {False}, hold_remove_time = NULL::timestamp, invoice_oid = NULL " \
                        f"FROM (VALUES ({', '.join(holds_removed)})) AS batch(patron_oid) " \
                        "WHERE overdues.patron_oid = batch.patron_oid")
    
    def excluded_allocations(self, allocations: str):
        allocation_list = allocations.split()
        insert_query = ""
        for allocation in allocation_list:
            insert_query += "(" + str(self.connection.get_checkout(id=allocation).json()['payload']['result'][0]['oid']) + ")," + '\n'
        
        if insert_query:
            self.db.run("INSERT INTO " \
                            "excluded_allocations (allocation_oid) " \
                        "VALUES " \
                            f"{insert_query.strip()[:-1]}" \
                        "ON CONFLICT (allocation_oid) DO NOTHING")

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

db.run("CREATE TABLE IF NOT EXISTS overdues (patron_oid INTEGER PRIMARY KEY, count INTEGER, hold_status BOOLEAN DEFAULT FALSE, fee_status BOOLEAN DEFAULT FALSE, hold_length INTEGER, hold_remove_time TIMESTAMP, invoice_oid INTEGER)")
db.run("CREATE TABLE IF NOT EXISTS excluded_allocations (allocation_oid INTEGER PRIMARY KEY, timeout TIMESTAMP)")

wco_conn = Connection(wco_userid, wco_password, wco_host)
oconn = Overdues(wco_conn, utils(wco_conn), db)

oconn.excluded_allocations(input("Excluded allocations (whitespace seperation): "))
oconn.update('1/23/2024')

#oconn.place_hold(14652305, wco_conn.centers['college'], message='foobar')