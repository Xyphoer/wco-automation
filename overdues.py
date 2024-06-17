from connection import Connection
from redmine import Texting, RedmineConnection, CannedMessages
from postgres import Postgres
from datetime import datetime, timedelta, timezone
from utils import utils, Repercussions

class Overdues:

    def __init__(self, connection: Connection, utilities: utils, rm_connection: RedmineConnection, texting: Texting, db_pass):
        self.connection = connection
        self.rm_connection = rm_connection
        self.texting = texting
        self.utils = utilities
        self.db = self._connect_to_db(db_pass)

        self.register_changes_email=''
        self.register_changes_name_first=''
        self.register_changes_name_last=''
        with open('config.txt', 'r') as config:
            for line in config:
                if "register_changes_email" in line.lower():
                    self.register_changes_email = line.split("=", maxsplit=1)[1].strip()
                if "register_changes_name_first" in line.lower():
                    self.register_changes_name_first = line.split("=", maxsplit=1)[1].strip()
                if "register_changes_name_last" in line.lower():
                    self.register_changes_name_last = line.split("=", maxsplit=1)[1].strip()
        if not (self.register_changes_email and self.register_changes_name_first and self.register_changes_name_last):
            print('Incomplete data on registrar changes contact info. Please provide data.')
            self.register_changes_email = input("Contact email: ")
            self.register_changes_name_first = input("Contact First Name: ")
            self.register_changes_name_last = input("Contact Last Name")

        self.session_registrar_changes = []
    
    def update(self, start_time: str, end_time: str = '') -> dict:
        self._process_returned_overdues(start_time, end_time)
        self._process_fines()
        self._remove_holds()
        self._process_current_overdues()
        self._process_expirations()
        self._process_lost()
        self._process_registrar_holds()
 
    def _connect_to_db(self, db_pass) -> Postgres:
        db = Postgres(f"dbname=postgres user=postgres password={db_pass}")
        db.run("CREATE EXTENSION IF NOT EXISTS intarray") # required for subracting array of ints from array of ints
        db.run("CREATE TABLE IF NOT EXISTS overdues (patron_oid INTEGER PRIMARY KEY, count INTEGER DEFAULT 0, hold_count INTEGER DEFAULT 0, fee_count INTEGER DEFAULT 0, hold_length INTERVAL DEFAULT CAST('0' AS INTERVAL), hold_remove_time TIMESTAMP, invoice_oids INTEGER[], registrar_hold_count INTEGER DEFAULT 0)")
        db.run("CREATE TABLE IF NOT EXISTS invoices (invoice_oid INTEGER, count INTEGER DEFAULT 0, hold_status BOOLEAN DEFAULT FALSE, fee_status BOOLEAN DEFAULT FALSE, registrar_hold BOOLEAN DEFAULT FALSE, hold_length INTERVAL DEFAULT CAST('0' AS INTERVAL), overdue_start_time TIMESTAMP, hold_remove_time TIMESTAMP, ck_oid INTEGER, patron_oid INTEGER, waived BOOLEAN DEFAULT FALSE, expiration TIMESTAMP, overdue_lost BOOLEAN DEFAULT FALSE, PRIMARY KEY(invoice_oid, ck_oid))")
        db.run("CREATE TABLE IF NOT EXISTS excluded_allocations (allocation_oid INTEGER PRIMARY KEY, processed TIMESTAMP)")
        db.run("CREATE TABLE IF NOT EXISTS history (time_ran TIMESTAMP, log_file TEXT)")
        return db
    
    def last_run(self) -> datetime:
        return self.db.one('SELECT time_ran FROM history ORDER BY time_ran DESC LIMIT 1')

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
    # On new - by checkout - process
    def place_hold(self, oid: int, checkout_center, allocation = None, end = None, overdue_time = None, message = '', update_db = True):
        account = self.connection.get_account(oid).json()
        overdue_count = self.db.one(f"SELECT count FROM overdues WHERE patron_oid = {oid}")
        self.connection.set_scope(checkout_center['oid'], 'checkoutCenter')
        invoice = self.connection.create_invoice(account['payload']['defaultAccount'], checkout_center['organization'], checkout_center, allocation=allocation,
                                                description=f"Invoice for violation of overdue policies: https://kb.wisc.edu/infolabs/131963. Previous overdue item count: {overdue_count if overdue_count else 0}").json()
        invoice_oid = invoice['payload']['oid']
        invoice = self.connection.update_invoice(invoice_oid, {"dueDate": None}).json()
        _hold = self.connection.apply_invoice_hold(invoice['payload'], message)
        ck_oid = allocation['oid'] if allocation else None

        if not invoice_oid:
            print(f"Failed to create invoice for patron with oid {oid}")  # should be better

        if update_db:
            if end:
                # get length of hold in float of days
                diff = end - datetime.now()
                hold_length = (diff.days if diff.days > 0 else 0) + round(diff.seconds / 60 / 60 / 24, 3) if end else 0

                # perhaps edit overdues table first (add overdue length), return the new hold_remove_time from that, which is now the hold remove time of the invoice table
                with self.db.get_cursor() as cursor:
                    cursor.run("INSERT INTO " \
                                    "overdues (patron_oid, hold_count, hold_length hold_remove_time, invoice_oids)" \
                                "VALUES " \
                                    "(%(oid)s, 1, CAST('%(hold_l)sD' AS INTERVAL), CAST(%(hold_rtime)s AS TIMESTAMP), %(i_id)s) " \
                                "ON CONFLICT (patron_oid) DO " \
                                    "UPDATE SET hold_count = overdues.hold_count + 1, hold_length = overdues.hold_length + EXCLUDED.hold_length, " \
                                        "hold_remove_time = overdues.hold_remove_time + EXCLUDED.hold_length, invoice_oids = overdues.invoice_oids || EXCLUDED.invoice_oids "\
                                "RETURNING hold_remove_time", oid=oid, hold_l=hold_length, hold_rtime=end, i_id=str({invoice_oid}))
                    back_hold_remove_time = cursor.fetchone()[0] # gives datetime.datetime object for extended hold_remove time of sequential invoices
                
                self.db.run("INSERT INTO " \
                                "invoices (invoice_oid, hold_status, hold_length, overdue_start_time, hold_remove_time, ck_oid, patron_oid)" \
                            "VALUES " \
                                "(%(i_id)s, %(hold_s)s, CAST('%(hold_l)sD' AS INTERVAL), CAST(%(o_stime)s AS TIMESTAMP), CAST(%(hold_rtime)s AS TIMESTAMP), %(c_id)s, %(oid)s) " \
                            "ON CONFLICT (invoice_oid) DO " \
                                "UPDATE SET hold_status = EXCLUDED.hold_status, hold_length = EXCLUDED.hold_length, overdue_start_time = EXCLUDED.overdue_start_time" \
                                    "hold_remove_time = EXCLUDED.hold_remove_time, ck_oid = EXCLUDED.ck_oid, patron_oid = EXCLUDED.patron_oid",
                            i_id = invoice_oid, hold_s=True, hold_l=hold_length, o_stime=overdue_time, hold_rtime=back_hold_remove_time, c_id = ck_oid, oid=oid)

            # For no end, process same. 0D will be added to interval and to hold_remove_time. Invoice table entry will have 0 day and no hold_remove_time. Add to overall when returned.
            # Also, keep hold_status/fee_status = true even if hold_length is 0 and hold_remove_time is NULL. Only remove when all invoice oids have been removed.
            else:
                self.db.run("INSERT INTO " \
                                "overdues (patron_oid, hold_count, invoice_oids)" \
                            "VALUES " \
                                "(%(oid)s, 1, %(i_id)s) " \
                            "ON CONFLICT (patron_oid) DO " \
                                "UPDATE SET hold_count = overdues.hold_count + 1, invoice_oids = overdues.invoice_oids || EXCLUDED.invoice_oids ",
                                oid=oid, i_id=str({invoice_oid}))
                
                self.db.run("INSERT INTO " \
                                "invoices (invoice_oid, hold_status, ck_oid, patron_oid, overdue_start_time)" \
                            "VALUES " \
                                "(%(i_id)s, %(hold_s)s, %(c_id)s, %(oid)s, CAST(%(o_stime)s AS TIMESTAMP)) " \
                            "ON CONFLICT (invoice_oid, ck_oid) DO " \
                                "UPDATE SET hold_status = EXCLUDED.hold_status, ck_oid = EXCLUDED.ck_oid, patron_oid = EXCLUDED.patron_oid, overdue_start_time = EXCLUDED.overdue_start_time",
                            i_id = invoice_oid, hold_s=True, c_id = ck_oid, oid=oid, o_stime=overdue_time)
            
            canned = CannedMessages(invoice_oid, self.connection, self.db).get_base()
            canned_subject, canned_description = canned['subject'], canned['description']
            person = self.connection.get_patron(oid, ['email', 'firstName', 'lastName']).json()['payload']
            ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
            self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], status_id=self.rm_connection.statuses['Resolved'], content=canned_description)

        
        return invoice['payload']

    # remove a specific hold
    def remove_hold(self, invoice_oid: int):
        invoice = self.connection.get_invoice(invoice_oid, ['person', 'checkoutCenter']).json()['payload']
        self.connection.set_scope(invoice['checkoutCenter']['oid'], "checkoutCenter")
        self.connection.remove_invoice_hold(invoice)  # NOTE: Works, but WCO thows 500 error if hold already gone
        self.connection.waive_invoice(invoice)

        patron_oid = self.db.one('SELECT patron_oid FROM invoices WHERE invoice_oid = %(i_oid)s', i_oid = invoice_oid)
        canned = CannedMessages(invoice_oid, self.connection, self.db).get_lifted() ## possible issues here if multiple holds
        canned_subject, canned_description = canned['subject'], canned['description']
        person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName']).json()['payload']
        ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
        self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], status_id=self.rm_connection.statuses['Resolved'], content=canned_description)

        # print(f"{invoice['person']['name']} -- {invoice['person']['userid']} -- Hold Removed")
        return invoice

    # On new - by checkout - process
    def place_fee(self, invoice_oid: int, cost: int):

        if type(invoice_oid) == int:
            invoice = self.connection.get_invoice(invoice_oid, properties=['payee']).json()['payload']
            self.connection.add_charge(invoice, amount=cost, subtype="Loss", text="")
            
            patron_oid = self.db.one('SELECT patron_oid FROM invoices WHERE invoice_oid = %(i_oid)s', i_oid = invoice_oid)
            canned = CannedMessages(invoice_oid, self.connection, self.db).get_charge()
            canned_subject, canned_description = canned['subject'], canned['description']
            person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName']).json()['payload']
            ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
            self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)
                
            self.db.run("UPDATE invoices " \
                        "SET fee_status = True " \
                        "WHERE invoice_oid = %(i_id)s", i_id = invoice_oid)
            self.db.run("UPDATE overdues " \
                        "SET fee_count = fee_count + 1 " \
                        "WHERE patron_oid = %(oid)s", oid=patron_oid)

            return invoice
        else:
            print(f"Could not place fee with invoice_oid: {invoice_oid}")  # clean to actually use wco responses to determine
    
    # get all current overdues and apply holds (if >1day or reserve) and update DB -- DONE: NEED TEST
    # On new - by checkout - process
    def _process_current_overdues(self):
        response = self.connection.get_current_overdue_allocations()

        # somewhat wasteful. Possibly check only when needed
        current_hold_allocs = self.db.all('SELECT ck_oid FROM invoices WHERE hold_status AND NOT waived')
        current_fine_allocs = self.db.all('SELECT ck_oid FROM invoices WHERE fee_status AND NOT waived')
        current_registrar_holds = self.db.all('SELECT ck_oid FROM invoices WHERE registrar_hold AND NOT waived')
        excluded_checkouts = self.db.all('SELECT allocation_oid FROM excluded_allocations')

        for allocation in response.json()['payload']['result']:
            center = allocation['checkoutCenter']
            patron_oid = allocation['patron']['oid']

            scheduled_end = datetime.strptime(allocation['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
            tz = timezone(timedelta(hours=-6), name='utc-6')
            #tz.dst = True

            # NOW BACKTRACKING
            # policy_start_date = datetime(year=2024, month=1, day=23, tzinfo=tz)
            # if scheduled_end < policy_start_date:
            #     scheduled_end = policy_start_date
            overdue_length = (datetime.now(tz=tz) - scheduled_end).days

            allocation_types = [item['rtype'] for item in allocation['items'] if item['action'].lower() == 'checkout']
            consequences = Repercussions(overdue_length, allocation_types).update()

            if allocation['oid'] not in excluded_checkouts:
                if consequences['Hold'] and allocation['oid'] not in excluded_checkouts:
                    invoice = False
                    if allocation['oid'] not in current_hold_allocs:  # only process a checkout once
                        #####
                        # LEGACY: Used to help convert between databases with good ck-oid's
                        # i_id = self.db.all('SELECT invoice_oid FROM invoices WHERE patron_oid = %(p_oid)s', p_oid = patron_oid)
                        # cks = self.connection.get_patron_checkouts(patron_oid, ['isOverdue']).json()['payload']['result']
                        # cks_count = len([ck for ck in cks if ck['isOverdue']])
                        # if len(i_id) == cks_count:
                        #     if cks_count == 1:
                        #         self.db.run('UPDATE invoices SET ck_oid = %(ck_oid)s WHERE invoice_oid = %(i_id)s', ck_oid = allocation['oid'], i_id = i_id[0])
                        #     else:
                        #         print("----")
                        #     continue
                        ######
                        invoice = self.place_hold(patron_oid, center, allocation, overdue_time=scheduled_end)
                        invoice_oid = invoice['oid']

                        try:
                            self.texting.add_checkout(allocation['checkoutCenter']['name'], allocation)
                        except Exception as e:
                            print(e)

                    else:
                        invoice_oids = self.db.all('SELECT invoice_oid FROM invoices WHERE ck_oid=%(id)s AND NOT waived', id=allocation['oid'])
                        invoice_oid = invoice_oids[0]
                        if len(invoice_oids) > 1:
                            print(f'checkout {allocation["oid"]} has multiple invoices, proceeding with {invoice_oid}')
                    if consequences['Fee']:
                        if allocation['oid'] not in current_fine_allocs:  # only one fee per invoice
                            charge = allocation['aggregateValueOut'] if allocation['aggregateValueOut'] else 2000 # value of checked out items only
                            fee_placed = self.place_fee(invoice_oid, charge)

                            try:
                                self.texting.add_checkout(allocation['checkoutCenter']['name'], allocation)
                            except Exception as e:
                                print(e)

                            if not fee_placed:
                                print(f"No fee placed on person with oid:{patron_oid}")
                        if consequences['Registrar Hold'] and allocation['oid'] not in current_registrar_holds:
                            # if this is their first registrar hold
                            if self.db.one("SELECT registrar_hold_count FROM overdues WHERE patron_oid = %(p_id)s", p_id = patron_oid) == 0:
                                canned = CannedMessages(invoice_oid, self.connection, self.db).canned_registrar_placed
                                canned_subject, canned_description = canned['subject'], canned['description']
                                person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName', 'name', 'barcode']).json()['payload']
                                ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                                self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                                self.session_registrar_changes.append((1, person['name'], person['barcode'], ticket.json()['helpdesk_ticket']['id']))

                                print(f'Registrar Hold placed for: {person["oid"]} -- {person["name"]} - ({person["barcode"]})')
                                
                            self.db.run("UPDATE invoices SET registrar_hold = True WHERE invoice_oid = %(i_id)s", i_id = invoice_oid)
                            self.db.run("UPDATE overdues SET registrar_hold_count = registrar_hold_count + 1 WHERE patron_oid = %(p_id)s", p_id = patron_oid)
        
        try:
            self.texting.ticketify()
        except Exception as e:
            print(e)

        return

    # get all returned overdues and resolve hold end date, fine, or fully create if needed. -- NOTE: Need fine implement & alloc with diff return times handler
    # on new - by checkout - process
    # possibly set an invoice due date with: self.connection.update_invoice(invoice_oid, {"dueDate": None}).json() ?
    def _process_returned_overdues(self, start_search_time: datetime, end_search_time: datetime): #  -> dict
        # update db with new overdue items for patrons (Note: only count if the checkout is completed)
        # update step: returns dictionary of changes
        insert_dict = {}

        current_hold_allocs = self.db.all('SELECT ck_oid FROM invoices WHERE hold_status AND NOT (waived OR overdue_lost)')  # should tidy up and not do one big query, but single ones when needed
        current_fine_allocs = self.db.all('SELECT ck_oid, invoice_oid FROM invoices WHERE fee_status AND NOT (waived OR overdue_lost)')
        # any checkout specified by staff via 'excluded_allocations' or a checkout that has been returned solely for the purpose of declaring lost, should not be processed as a returned overdue checkout.
        excluded_checkouts = self.db.all('SELECT allocation_oid FROM excluded_allocations')
        excluded_checkouts.extend(self.db.all('SELECT ck_oid FROM invoices WHERE overdue_lost'))

        # if not specific_checkouts:
        allocations = self.connection.get_completed_overdue_allocations(start_search_time, end_search_time).json()['payload']['result']
        # else:
        #     allocations = specific_checkouts

        for allocation in allocations:
            if allocation['oid'] not in excluded_checkouts:
                # retrieve policy consequences based on allocation items, types, and overdue length (planned incorporation of count here instead of in sql upserts)
                conseq, end_time, checkout_center = self.utils.get_overdue_consequence(allocation)
                # used to decriment fee_count and/or registrar_count in database if one is removed
                fee_status, registrar_status = 0, 0

                # If they have a fine, remove it as they returned the item
                for entry in current_fine_allocs:
                    if allocation['oid'] == entry[0]:
                        struck = False
                        fee_status = 1
                        invoice = self.connection.get_invoice(entry[1]).json()['payload']
                        invoice_lines = self.connection.get_invoice_lines(invoice).json()['payload']['result']
                        for invoice_line in invoice_lines:
                            if invoice_line['type'] == 'CHARGE' and not invoice_line['struck']:
                                self.connection.set_scope(allocation['checkoutCenter']['oid'], "checkoutCenter")
                                self.connection.strike_invoice_line(invoice, invoice_line)  # APPLY HOLD AGAIN, PAYING REMOVES IT
                                struck = True
                        if struck:
                            self.connection.apply_invoice_hold(invoice)
                        
                        # check if invoice had registrar hold
                        reg_hold = self.db.one("SELECT registrar_hold FROM invoices WHERE invoice_oid = %(i_id)s", i_id = entry[1])
                        if conseq['Registrar Hold'] and reg_hold:
                            registrar_status = 1 # used to decriment overall count
                            # check if only registrar hold on patrons account
                            if self.db.one("SELECT registrar_hold_count FROM overdues WHERE patron_oid = %(p_id)s", p_id = allocation['patron']['oid']) == 1:
                                canned = CannedMessages(entry[1], self.connection, self.db).canned_registrar_removed
                                canned_subject, canned_description = canned['subject'], canned['description']
                                person = self.connection.get_patron(allocation['patron']['oid'], ['email', 'firstName', 'lastName', 'barcode']).json()['payload']
                                ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                                self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                                self.session_registrar_changes.append((0, person['name'], person['barcode'], ticket.json()['helpdesk_ticket']['id']))

                                print(f"Items returned, registrar hold removed for oid: {person['oid']} -- {person['name']} - ({person['barcode']})")

                            # included updating of db in overall updates
                            ##self.db.run("UPDATE invoices SET registrar_hold = False WHERE invoice_oid = %(i_id)s", i_id = entry[1])
                            ##self.db.run("UPDATE overdues SET registrar_hold_count = registrar_hold_count - 1 WHERE patron_oid = %(p_id)s", p_id=allocation['patron']['oid'])

                # handle partial returns before due date
                item_count = 0
                for item in allocation['items']:
                    item_returned = datetime.strptime(item['realReturnTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    allocation_due = datetime.strptime(item['returnTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    # 10 minute grace period before determining if item is truly overdue (24 grace period for overall overdues for non-reserves still applies)
                    if item_returned > allocation_due + timedelta(minutes=10):
                        item_count += 1

                ## processing checkouts singularly, no checkout should repeat.
                # try:
                #     insert_dict[allocation['oid']][0] += item_count
                #     insert_dict[allocation['oid']][1:] = ['True' if conseq['Hold'] else 'False',  # hold_status
                #                                                     'False',                                # fee_status ALWAYS false for returned items
                #                                                     conseq['Hold'],                         # hold_length
                #                                                     f"'{end_time + timedelta(days=conseq['Hold'])}'" if conseq['Hold'] else 'NULL', # hold_remove_time (from ck end time)
                #                                                     checkout_center,    # checkout center for hold
                #                                                     allocation,
                #                                                     fee_status,
                #                                                     registrar_status]

                # except KeyError as e:
                ##
                insert_dict[allocation['oid']] = [item_count,
                                                  'True' if conseq['Hold'] else 'False',  # hold_status
                                                  'False',                                # fee_status ALWAYS false for returned items
                                                  conseq['Hold'],                         # hold_length
                                                  f"CAST('{end_time + timedelta(days=conseq['Hold'])}' AS TIMESTAMP)" if conseq['Hold'] else 'NULL', # hold_remove_time (from ck end time)
                                                  checkout_center,    # checkout center for hold
                                                  allocation,         # allocation to attach the hold to, as well as for extra invoice information
                                                  fee_status,         # amount to decriment from database fee_count
                                                  registrar_status]   # amount to decriment from database registrar_hold_count

        for key, value in insert_dict.items():
            try:
                invoice_oid = False

                ## Count potentially be moved into loop for allocs
                # get invoice information and email the patron with information now that they've returned
                # place hold if one is not already in place
                if key not in current_hold_allocs:
                    if value[1] == 'True':
                        invoice = self.place_hold(value[6]['patron']['oid'], checkout_center=value[5], allocation=value[6], update_db=False)
                        invoice_oid = invoice['oid']

                else:
                    invoice_oid = self.db.one('SELECT invoice_oid FROM invoices WHERE ck_oid = %(a_id)s', a_id = value[6]['oid'])
                    invoice = self.connection.get_invoice(invoice_oid).json()['payload']

                if invoice_oid:
                    # Insert individually as processing:
                    ## DB more up to date if issue is encountered
                    ## Simpler solution for one given patron having multiple new invoices (both need to append)
                    ## Relatively few new invoices to process on a typical run so slightly slower updating is acceptable

                    ### NOTE: Overdue amount thresholds are Greater Than, not only once
                    ### NOTE: only update count and hold_count when not already processed by current_overdue_checkouts (i.e. had to create invoice) (if already stored, was already created)
                    # NOTE: CURRENT ISSUE: ambiguity in using current checkout count for determining hold length. If a checkout has been processed by process_current_overdues it will count the current amount, however if it hasn't, it wont.
                    # In _process_fines it will always take the current amount into account. Possible fixes: Make a query first to see if it's been processed before (i.e. invoice exists) and process differently depending on the result.

                    # using nested case statements unsures overdues.count is always the latest in the comparison, but is messy. Test performance with seperate query
                    with self.db.get_cursor() as cursor:
                        cursor.run("INSERT INTO " \
                                        "overdues (patron_oid, count, hold_count, fee_count, hold_length, hold_remove_time, invoice_oids) " \
                                    "VALUES " \
                                        "(%(oid)s, %(i_count)s, %(hold_c)s, 0, CAST('%(hold_l)sD' AS INTERVAL)," + f" {value[4]}, " + "%(i_id)s) " \
                                    "ON CONFLICT (patron_oid) DO " \
                                        "UPDATE SET count = overdues.count + EXCLUDED.count, " \
                                        "hold_count = CASE WHEN %(i_id_plain)s = ANY(overdues.invoice_oids) THEN overdues.hold_count ELSE overdues.hold_count + EXCLUDED.hold_count END, " \
                                        "fee_count = overdues.fee_count - %(fee_c)s, " \
                                        "hold_length = CASE " \
                                            "WHEN overdues.count + EXCLUDED.count >= 12 " \
                                                "THEN '0'::INTERVAL " \
                                            "WHEN overdues.count + EXCLUDED.count >= 10 " \
                                                "THEN overdues.hold_length + '180D'::INTERVAL " \
                                            "WHEN overdues.count + EXCLUDED.count >= 5 " \
                                                "THEN overdues.hold_length + '90D'::INTERVAL " \
                                            "ELSE overdues.hold_length + EXCLUDED.hold_length " \
                                        "END, " \
                                        "hold_remove_time = CASE " \
                                            "WHEN overdues.count + EXCLUDED.count >= 12 " \
                                                "THEN NULL::TIMESTAMP " \
                                            "WHEN overdues.count + EXCLUDED.count >= 10 AND overdues.hold_remove_time IS NULL " \
                                                "THEN (EXCLUDED.hold_remove_time - EXCLUDED.hold_length + '180D'::INTERVAL)::TIMESTAMP " \
                                            "WHEN overdues.count + EXCLUDED.count >= 10 AND overdues.hold_remove_time IS NOT NULL " \
                                                "THEN overdues.hold_remove_time + '180D'::INTERVAL " \
                                            "WHEN overdues.count + EXCLUDED.count >= 5 AND overdues.hold_remove_time IS NULL " \
                                                "THEN (EXCLUDED.hold_remove_time - EXCLUDED.hold_length + '90D'::INTERVAL)::TIMESTAMP " \
                                            "WHEN overdues.count + EXCLUDED.count >= 5 AND overdues.hold_remove_time IS NOT NULL " \
                                                "THEN overdues.hold_remove_time + '90D'::INTERVAL " \
                                            "WHEN overdues.hold_remove_time IS NULL " \
                                                "THEN EXCLUDED.hold_remove_time " \
                                            "ELSE overdues.hold_remove_time + EXCLUDED.hold_length " \
                                        "END, " \
                                        "invoice_oids = CASE WHEN %(i_id_plain)s = ANY(overdues.invoice_oids) THEN overdues.invoice_oids ELSE overdues.invoice_oids || EXCLUDED.invoice_oids END, "\
                                        "registrar_hold_count = overdues.registrar_hold_count - %(r_hold_c)s " \
                                    "RETURNING hold_remove_time, overdues.count",
                                                                oid        = value[6]['patron']['oid'],
                                                                i_count    = value[0],
                                                                hold_c     = 1 if value[1]=='True' else 0,
                                                                fee_c      = value[7],
                                                                hold_l     = value[3],
                                                                i_id       = str({invoice_oid}) if invoice_oid else '{}',
                                                                i_id_plain = invoice_oid if invoice_oid else -2,
                                                                r_hold_c   = value[8]) # hold_rtime = value[4],
                        back_hold_remove_time, overdues_count = cursor.fetchone() # gives datetime.datetime object for extended hold_remove time of sequential invoices
                    
                    hold_len = value[3]
                    if overdues_count >= 12:
                        hold_len = 0
                    elif overdues_count >= 10:
                        hold_len = 180
                    elif overdues_count >= 5:
                        hold_len = 90
                    
                    # add/update invoice entry in invoices db.
                    ## When updating:
                    #### count: No change. Both should be the same
                    #### hold_status: No change. hold should always be in place here
                    #### fee_status: Take new value. Fee should be removed.
                    #### hold_length: Take new value. Just calculated final hold_length
                    #### hold_remove_time: Take new value. Just calculated
                    #### ck_oid: No change. Both should be the same
                    #### patron_oid: No change: Both should be the same
                    #### registrar_hold: Should be removed.
                    self.db.run("INSERT INTO " \
                                    "invoices (invoice_oid, count, hold_status, fee_status, hold_length, overdue_start_time, hold_remove_time, ck_oid, patron_oid, expiration, registrar_hold) " \
                                "VALUES " \
                                    "(%(i_id)s, %(i_count)s, %(hold_s)s, False, CAST('%(hold_l)sD' AS INTERVAL), CAST(%(o_stime)s AS TIMESTAMP), CAST(%(hold_rtime)s AS TIMESTAMP), %(c_oid)s, %(p_oid)s, CAST(%(expire)s AS TIMESTAMP), False)" \
                                "ON CONFLICT (invoice_oid, ck_oid) DO " \
                                    "UPDATE SET count = EXCLUDED.count, hold_status = EXCLUDED.hold_status, fee_status = EXCLUDED.fee_status, " \
                                        "hold_length = EXCLUDED.hold_length, hold_remove_time = EXCLUDED.hold_remove_time, " \
                                        "expiration = EXCLUDED.expiration, registrar_hold = False", i_id = invoice_oid,
                                                                                                    i_count = value[0],
                                                                                                    hold_s = value[1],
                                                                                                    hold_l = hold_len,
                                                                                                    o_stime = datetime.strptime(value[6]['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z'),
                                                                                                    hold_rtime = back_hold_remove_time,
                                                                                                    c_oid = key,
                                                                                                    p_oid = value[6]['patron']['oid'],
                                                                                                    expire = back_hold_remove_time + timedelta(days = ((365 * 4) - hold_len)))
                    # email only if invoice exists. This whole setup should be reworked
                    if key not in current_hold_allocs:
                        if value[1] == 'True':
                            patron_oid = self.db.one('SELECT patron_oid FROM invoices WHERE invoice_oid = %(i_oid)s', i_oid = invoice_oid)
                            canned = CannedMessages(invoice_oid, self.connection, self.db).get_base()
                            canned_subject, canned_description = canned['subject'], canned['description']
                            person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName']).json()['payload']
                            ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                            self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                    else:
                        patron_oid = self.db.one('SELECT patron_oid FROM invoices WHERE invoice_oid = %(i_oid)s', i_oid = invoice_oid)
                        canned = CannedMessages(invoice_oid, self.connection, self.db).get_returned()
                        canned_subject, canned_description = canned['subject'], canned['description']
                        person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName']).json()['payload']
                        ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                        self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)
                ### LEGACY from processing <1 day non-reserve overdues. No longer process, repercussions not necissary
                # else:
                    # invoice_oid = -1 # signifies <1 day overdue of non-reserve. Should make own table eventually (stop-gap) | use negative invoice_oid values for differentiation
                    # self.db.run("INSERT INTO " \
                    #                 "invoices (invoice_oid, count, overdue_start_time, ck_oid, patron_oid, expiration, registrar_hold) " \
                    #             "VALUES " \
                    #                 "(%(i_id)s, %(i_count)s, CAST(%(o_stime)s AS TIMESTAMP), %(c_oid)s, %(p_oid)s, '%(expire)s'::TIMESTAMP)" \
                    #             "ON CONFLICT (invoice_oid) DO " \
                    #                 "UPDATE SET count = EXCLUDED.count, expiration = EXCLUDED.expiration", i_id = invoice_oid,
                    #                                                                                 i_count = value[0],
                    #                                                                                 o_stime = datetime.strptime(value[6]['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z'),
                    #                                                                                 c_oid = key,
                    #                                                                                 p_oid = value[6]['patron']['oid'],
                    #                                                                                 expire = back_hold_remove_time + timedelta(days = ((365 * 4) - hold_len)))                                                                                                    )
            except Exception as e:
                print(key, value, invoice_oid)
                print(e)
            
        self.db.run(f"INSERT INTO history (time_ran) VALUES ('{end_search_time.isoformat()}')") # should isolate to own function running at end
        
        return

    # check for those who have paid their fine, and resolve hold end date if they have NOTE: Done   ALSO: return and delete (paying fine equates to lost) NOTE: Done, UPGRADE PATH
    # NOTE: still open $0.00 holds count as 'Paid' not 'Pending' thus are not open. (Still can have hold). Staff can 'strike' charges when they are paid.
    # NOTE: UPDATEing singly for reconciliation of hold_remove_time
    # On new - by checkout - process
    def _process_fines(self):
        fined_patrons = self.db.all('SELECT patron_oid, ck_oid, invoice_oid, registrar_hold FROM invoices WHERE fee_status AND NOT waived')

        for patron_oid, ck_oid, invoice_oid, registrar_hold in fined_patrons:
            invoice = self.connection.get_invoice(invoice_oid, ['datePaid', 'isHold']).json()['payload']
            if invoice['datePaid']:

                person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName', 'name', 'barcode']).json()['payload']
                print(f"Patron oid: {patron_oid} -- paid fine -- {person['name']} - ({person['barcode']}) -- Return & Delete item") # can do automatically
                if self.db.one("SELECT registrar_hold_count FROM overdues WHERE patron_oid = %(p_id)s", p_id = patron_oid) == 1:
                    canned = CannedMessages(invoice_oid, self.connection, self.db).canned_registrar_removed
                    canned_subject, canned_description = canned['subject'], canned['description']
                    
                    ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                    self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                    self.session_registrar_changes.append((0, person['name'], person['barcode'], ticket.json()['helpdesk_ticket']['id']))

                    print(f"Patron oid: {patron_oid} -- paid fine -- {person['name']} - ({person['barcode']}) -- Removed Registrar Hold")

                date_paid = datetime.strptime(invoice['datePaid'], '%Y-%m-%dT%H:%M:%S.%f%z')

                # can use even for declared lost items since repercussions won't change after 6 months, so it doesn't matter the calculated amount will use the lost-returned date
                alloc = self.connection.get_allocation(ck_oid, properties=['realEndTime', 'scheduledEndTime', 'realReturnTime', 'rtype', 'checkoutCenter']).json()['payload']
                conseq, _, _ = self.utils.get_overdue_consequence(alloc)

                canned = CannedMessages(invoice_oid, self.connection, self.db).get_returned()
                canned_subject, canned_description = canned['subject'], canned['description']
                person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName']).json()['payload']
                ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                with self.db.get_cursor() as cursor:
                    ### NOTE: invoice must already be created for this, and thus count and hold_count are already up to date. Thus don't update
                    cursor.run("UPDATE overdues SET " \
                                    "fee_count = fee_count - 1, " \
                                    "hold_length = CASE " \
                                        "WHEN count >= 12 " \
                                            "THEN '0'::INTERVAL " \
                                        "WHEN count >= 10 " \
                                            "THEN hold_length + '180D'::INTERVAL " \
                                        "WHEN count >= 5 " \
                                            "THEN hold_length + '90D'::INTERVAL " \
                                        "ELSE hold_length + %(base_extended)s"
                                    "END, " \
                                    "hold_remove_time = CASE " \
                                        "WHEN count >= 12 " \
                                            "THEN NULL::TIMESTAMP " \
                                        "WHEN count >= 10 AND (hold_remove_time < 'NOW'::TIMESTAMP OR hold_remove_time IS NULL) " \
                                            "THEN (%(paid_date)s::TIMESTAMP + '180D'::INTERVAL)::TIMESTAMP " \
                                        "WHEN count >= 10 " \
                                            "THEN (hold_remove_time + '180D'::INTERVAL)::TIMESTAMP " \
                                        "WHEN count >= 5 AND (hold_remove_time < 'NOW'::TIMESTAMP OR hold_remove_time IS NULL) " \
                                            "THEN (%(paid_date)s::TIMESTAMP + '90D'::INTERVAL)::TIMESTAMP " \
                                        "WHEN count >= 5 " \
                                            "THEN (hold_remove_time + '90D'::INTERVAL)::TIMESTAMP " \
                                        "WHEN hold_remove_time < 'NOW'::TIMESTAMP OR hold_remove_time IS NULL" \
                                            "THEN %(paid_length)s::TIMESTAMP " \
                                        "ELSE hold_remove_time + %(base_extended)s END " \
                                    "WHERE patron_oid = %(p_oid)s " \
                                    "RETURNING hold_remove_time, count",
                                                                    paid_date     = date_paid,
                                                                    paid_length   = {date_paid + timedelta(days=conseq["Hold"])},
                                                                    base_extended = f'{conseq["Hold"]}D::INTERVAL')
                    back_hold_remove_time, overdues_count = cursor.fetchone() # gives datetime.datetime object for extended hold_remove time of sequential invoices
                
                hold_len = conseq["Hold"]
                if overdues_count >= 12:
                    hold_len = 0
                elif overdues_count >= 10:
                    hold_len = 180
                elif overdues_count >= 5:
                    hold_len = 90

                self.db.run("UPDATE invoices SET " \
                                "fee_status = false, " \
                                "registrar_hold = false, " \
                                "hold_length = %(hold_l)s" \
                                "hold_remove_time = %(hold_rtime)s::TIMESTAMP " \
                            "WHERE invoice_oid = %(i_oid)s", hold_l = hold_len, hold_rtime = back_hold_remove_time, i_oid = invoice_oid)

    # remove holds on patrons who have reached the designated time of removal.
    # On new - by checkout - process
    def _remove_holds(self):
        now = datetime.now()
        holds_removed = {}
        invoice_oids = []

        potential_holds = self.db.all('SELECT patron_oid, hold_length, hold_remove_time, invoice_oid FROM invoices WHERE hold_status AND NOT waived')

        for patron_oid, hold_length, hold_remove_time, invoice_oid in potential_holds:
            if hold_remove_time and hold_remove_time < now:
                self.remove_hold(invoice_oid)
                invoice_oids.append(invoice_oid)
                if patron_oid in holds_removed:
                    holds_removed[patron_oid]['amount'] += 1
                    holds_removed[patron_oid]['length'] += hold_length
                    holds_removed[patron_oid]['invoices'].append(invoice_oid)
                else:
                    holds_removed[patron_oid] = {'amount': 1, 'length': hold_length, 'invoices': [invoice_oid]}
        
        if holds_removed:
            insert_str = ", ".join([f"({oid_key}, {holds_removed[oid_key]['amount']}, '{holds_removed[oid_key]['length']}'::INTERVAL, '{set(holds_removed[oid_key]['invoices'])}'::integer[])" for oid_key in holds_removed.keys()])
            self.db.run("UPDATE overdues SET " \
                            "hold_count = overdues.hold_count - batch.hold_amount, hold_length = overdues.hold_length - batch.hold_length, " \
                            "hold_remove_time = CASE " \
                                "WHEN overdues.hold_remove_time < 'NOW'::TIMESTAMP " \
                                    "THEN NULL::TIMESTAMP " \
                                "ELSE overdues.hold_remove_time END, " \
                            "invoice_oids = overdues.invoice_oids - batch.invoice_oids "\
                        f"FROM (VALUES {insert_str}) AS batch(patron_oid, hold_amount, hold_length, invoice_oids) " \
                        "WHERE overdues.patron_oid = batch.patron_oid")
            self.db.run("UPDATE invoices SET " \
                            "WAIVED = true " \
                        "WHERE invoice_oid IN %(i_ids)s", i_ids = tuple(invoice_oids))
    
    def _process_lost(self):
        lost_overdues = self.db.all("SELECT invoice_oid, ck_oid FROM invoices WHERE overdue_start_time < ('NOW'::TIMESTAMP - '6Months'::INTERVAL) AND NOT overdue_lost AND NOT waived AND hold_remove_time IS NULL")
        year_now = datetime.now().year
        prev_lost = self.db.all(f"SELECT invoice_oid, ck_oid FROM invoices WHERE overdue_lost AND overdue_start_time > CAST('01-01-{year_now}' AS TIMESTAMP)")

        # need safety for if folder doesn't exist, and to make it
        with open(f"../Lost Logs/Lost Items {datetime.now().isoformat(timespec='seconds').replace(':','_')}.csv", 'w') as csv:
            csv.write('item oid, item name, item serial number, item barcode, item type path, item creation date, checkout id, patron name, patron wiscard, patron status\n')
            
            for lost_ck in prev_lost:
                invoice_oid, allocation_oid = lost_ck[0], lost_ck[1]
                alloc = self.connection.get_allocation(allocation_oid, ['uniqueId', 'scheduledEndTime', 'checkoutCenter',
                    {'property': 'patron',
                        'subProperties': ['name', 'barcode', 'status']},
                    {'property': 'items',
                        'subProperties': ['name',
                                            {'property': 'resource',
                                                'subProperties': ['serialNumber', 'creationDate', 'resourceTypePath', 'barcode']
                                            }
                                        ]
                    }]).json()
                for item in alloc['payload']['items']:
                    csv.write(', '.join([str(item['resource']['oid']),
                                        item['name'],
                                        str(item['resource']['serialNumber']),
                                        item['resource']['barcode'],
                                        ''.join(item['resource']['resourceTypePath']),
                                        datetime.strptime(item['resource']['creationDate'], '%Y-%m-%dT%H:%M:%S.%f%z').isoformat(sep=' ', timespec='seconds'),
                                        alloc['payload']['uniqueId'],
                                        alloc['payload']['patron']['name'],
                                        alloc['payload']['patron']['barcode'],
                                        alloc['payload']['patron']['status']]) + '\n')

            for lost_ck in lost_overdues:
                invoice_oid, allocation_oid = lost_ck[0], lost_ck[1]

                #stopgap - cleanup
                if invoice_oid == -1:
                    continue # should actually delete references -- add later

                alloc = self.connection.get_allocation(allocation_oid, ['uniqueId', 'scheduledEndTime', 'checkoutCenter',
                    {'property': 'patron',
                        'subProperties': ['name', 'barcode', 'status']},
                    {'property': 'items',
                        'subProperties': ['name',
                                            {'property': 'resource',
                                                'subProperties': ['serialNumber', 'creationDate', 'resourceTypePath', 'barcode']
                                            }
                                        ]
                    }]).json()
                
                self.connection.set_scope(alloc['payload']['checkoutCenter']['oid'], 'checkoutCenter')
                self.connection.return_allocation(alloc['payload'])

                for item in alloc['payload']['items']:
                    rem = self.connection.delete_resource(item['resource']['oid'])
                    if type(rem) == str:
                        print(alloc['payload']['oid'], rem)

                    csv.write(', '.join([str(item['resource']['oid']),
                                        item['name'],
                                        str(item['resource']['serialNumber']),
                                        item['resource']['barcode'],
                                        ''.join(item['resource']['resourceTypePath']),
                                        datetime.strptime(item['resource']['creationDate'], '%Y-%m-%dT%H:%M:%S.%f%z').isoformat(sep=' ', timespec='seconds'),
                                        alloc['payload']['uniqueId'],
                                        alloc['payload']['patron']['name'],
                                        alloc['payload']['patron']['barcode'],
                                        alloc['payload']['patron']['status']]) + '\n')

                self.db.run("UPDATE invoices SET overdue_lost = True WHERE ck_oid = %(ck_oid)s", ck_oid = allocation_oid)

                canned = CannedMessages(invoice_oid, self.connection, self.db).get_lost()
                canned_subject, canned_description = canned['subject'], canned['description']
                person = self.connection.get_patron(alloc['payload']['patron']['oid'], ['email', 'firstName', 'lastName', 'name', 'barcode']).json()['payload']
                ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)
        
        # maybe do resources instead of full checkouts?
        allocations = input("Lost Returned allocations (whitespace seperation): ")
        allocation_list = allocations.split()

        for allocation in allocation_list:
            alloc_oid = self.connection.get_checkout(id=allocation if not allocation.isdigit() else 'CK-' + allocation).json()['payload']['result'][0]['oid']
            invoice_oid, patron_oid = self.db.one('SELECT invoice_oid, patron_oid FROM invoices WHERE ck_oid = %(ck_oid)s', ck_oid = alloc_oid)
            resources = self.connection.get_allocation(alloc_oid, properties=['items']).json()['payload']['items']
            for resource in resources:
                self.connection.undelete_resource(resource['resource']['oid'])

            date_back = datetime.now()

            ### NOTE: Very similar to _process_fines
            # can use even for declared lost items since repercussions won't change after 6 months, so it doesn't matter the calculated amount will use the lost-returned date
            alloc = self.connection.get_allocation(alloc_oid, properties=['realEndTime', 'scheduledEndTime', 'realReturnTime', 'rtype', 'checkoutCenter']).json()['payload']
            conseq, _, _ = self.utils.get_overdue_consequence(alloc)

            with self.db.get_cursor() as cursor:
                ### NOTE: invoice must already be created for this, and thus count and hold_count are already up to date. Thus don't update
                cursor.run("UPDATE overdues SET " \
                                "fee_count = fee_count - 1, " \
                                "hold_length = CASE " \
                                    "WHEN count >= 12 " \
                                        "THEN '0'::INTERVAL " \
                                    "WHEN count >= 10 " \
                                        "THEN hold_length + '180D'::INTERVAL " \
                                    "WHEN count >= 5 " \
                                        "THEN hold_length + '90D'::INTERVAL " \
                                    "ELSE hold_length + %(base_extended)s"
                                "END, " \
                                "hold_remove_time = CASE " \
                                    "WHEN count >= 12 " \
                                        "THEN NULL::TIMESTAMP " \
                                    "WHEN count >= 10 AND (hold_remove_time < 'NOW'::TIMESTAMP OR hold_remove_time IS NULL) " \
                                        "THEN (%(return_date)s::TIMESTAMP + '180D'::INTERVAL)::TIMESTAMP " \
                                    "WHEN count >= 10 " \
                                        "THEN (hold_remove_time + '180D'::INTERVAL)::TIMESTAMP " \
                                    "WHEN count >= 5 AND (hold_remove_time < 'NOW'::TIMESTAMP OR hold_remove_time IS NULL) " \
                                        "THEN (%(return_date)s::TIMESTAMP + '90D'::INTERVAL)::TIMESTAMP " \
                                    "WHEN count >= 5 " \
                                        "THEN (hold_remove_time + '90D'::INTERVAL)::TIMESTAMP " \
                                    "WHEN hold_remove_time < 'NOW'::TIMESTAMP OR hold_remove_time IS NULL" \
                                        "THEN %(return_length)s::TIMESTAMP " \
                                    "ELSE hold_remove_time + %(base_extended)s END " \
                                "WHERE patron_oid = %(p_oid)s " \
                                "RETURNING hold_remove_time, count",
                                                                return_date   = date_back,
                                                                return_length   = date_back + timedelta(days=conseq["Hold"]),
                                                                base_extended = f'{conseq["Hold"]}D::INTERVAL',
                                                                p_oid = patron_oid)
                back_hold_remove_time, overdues_count = cursor.fetchone() # gives datetime.datetime object for extended hold_remove time of sequential invoices
            
            hold_len = conseq["Hold"]
            if overdues_count >= 12:
                hold_len = 0
            elif overdues_count >= 10:
                hold_len = 180
            elif overdues_count >= 5:
                hold_len = 90

            self.db.run("UPDATE invoices SET " \
                            "fee_status = false, " \
                            "registrar_hold = false, " \
                            "hold_length = %(hold_l)s, " \
                            "hold_remove_time = %(hold_rtime)s::TIMESTAMP, " \
                            "overdue_lost = False, "
                        "WHERE invoice_oid = %(i_oid)s", hold_l = hold_len, hold_rtime = back_hold_remove_time, i_oid = invoice_oid)
            

            if self.db.one("SELECT registrar_hold_count FROM overdues WHERE patron_oid = %(p_id)s", p_id = patron_oid) == 1:
                canned = CannedMessages(invoice_oid, self.connection, self.db).canned_registrar_removed
                canned_subject, canned_description = canned['subject'], canned['description']
                person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName', 'name', 'barcode']).json()['payload']

                print(f"Patron oid: {patron_oid} -- returned lost item -- {person['name']} - ({person['barcode']}) -- Removed Registrar Hold")

                ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                self.session_registrar_changes.append((0, person['name'], person['barcode'], ticket.json()['helpdesk_ticket']['id']))

            # Email
            canned = CannedMessages(invoice_oid, self.connection, self.db).get_returned()
            canned_subject, canned_description = canned['subject'], canned['description']
            person = self.connection.get_patron(patron_oid, ['email', 'firstName', 'lastName']).json()['payload']
            ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
            self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)
    
    def excluded_allocations(self, allocations: str):
        allocation_list = allocations.split()
        insert_query = ""
        for allocation in allocation_list:
            ck_oid = self.connection.get_checkout(id=allocation if not allocation.isdigit() else 'CK-' + allocation).json()['payload']['result'][0]['oid']
        
            self.db.run("INSERT INTO " \
                            "excluded_allocations (allocation_oid) " \
                        "VALUES " \
                            "(%(ck_oid)s)" \
                        "ON CONFLICT (allocation_oid) DO NOTHING", ck_oid = ck_oid)
                        # maybe on conflict refresh expiration
        
        # process un-processed excluded_allocations (should just be the newly added ones above)
        un_processed_allocs = self.db.all("SELECT allocation_oid FROM excluded_allocations WHERE processed IS NULL")

        if un_processed_allocs:
            # if the allocations has previously been processed, need to remove that processing
            pre_processed = self.db.all("SELECT invoice_oid, patron_oid, ck_oid, registrar_hold FROM invoices WHERE ck_oid=ANY(%(a_id)s)", a_id = un_processed_allocs)
        else:
            pre_processed = []
        for i_oid, p_oid, ck_oid, registrar_status in pre_processed:
            self.remove_hold(i_oid)
            if registrar_status:
                # if this is their only registrar hold
                if self.db.one("SELECT registrar_hold_count FROM overdues WHERE patron_oid = %(p_id)s", p_id = p_oid) == 1:
                    canned = CannedMessages(i_oid, self.connection, self.db).canned_registrar_removed
                    canned_subject, canned_description = canned['subject'], canned['description']
                    person = self.connection.get_patron(p_oid, ['email', 'firstName', 'lastName', 'name', 'barcode']).json()['payload']
                    ticket = self.rm_connection.create_ticket(canned_subject, person['email'], person['firstName'], person['lastName'], '', self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
                    self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], canned_description)

                    self.session_registrar_changes.append((0, person['name'], person['barcode'], ticket.json()['helpdesk_ticket']['id']))

                    print(f'Excluded Registrar Hold Patron - Removed: {p_oid} -- {person["name"]} - ({person["barcode"]})')

            with self.db.get_cursor() as cursor:
                cursor.run("DELETE FROM invoices WHERE ck_oid = %(ck_oid)s RETURNING hold_status, fee_status", ck_oid = ck_oid)
                prev_status = cursor.fetchone()
                
            self.db.run("UPDATE overdues SET hold_count = hold_count - %(hold_amount)s, " \
                            "fee_count = fee_count - %(fee_amount)s, " \
                            "registrar_hold_count = registrar_hold_count - %(reg_hold)s, " \
                            "invoice_oids = invoice_oids - '{%(i_id)s}'::integer[]"
                        "WHERE patron_oid = %(p_id)s",
                            hold_amount = int(prev_status[0]),
                            fee_amount = int(prev_status[1]),
                            reg_hold = int(registrar_status),
                            i_id = i_oid,
                            p_id = p_oid) # convert previous hold/fee/registrar status to 1/0 for updating overdues
        
        if un_processed_allocs:
            self.db.run("UPDATE excluded_allocations SET processed = %(proc_date)s WHERE allocation_oid IN %(a_id)s",
                        proc_date = datetime.now(), a_id = un_processed_allocs)

    def _process_expirations(self):
        # process expired invoices | should emails be sent?
        back = ()
        with self.db.get_cursor() as cursor:
            cursor.run("DELETE FROM invoices WHERE expiration < 'NOW'::TIMESTAMP RETURNING count, patron_oid")
            back = cursor.fetchone()

        if back:
            for count, oid in back:
                self.db.run("UPDATE overdues SET count = count - %(r_count)s WHERE patron_oid = %(p_oid)s", r_count = count, p_oid = oid)
        
        # process expired exluded allocations (expire 1 year after being processed)
        with self.db.get_cursor() as cursor:
            cursor.run("DELETE FROM excluded_allocations WHERE processed + '1Y'::INTERVAL < 'NOW'::TIMESTAMP RETURNING allocation_oid")
            back = cursor.fetchone() # to be used for logging
    
    def _process_registrar_holds(self):
        message_content_add = ""
        message_content_remove = ""
        description = ""

        for register_change in self.session_registrar_changes:
            if register_change[0] == 1:
                message_content_add += f"- {register_change[1]} - ({register_change[2]}) - ticket: {register_change[3]}\n"
            else:
                message_content_remove += f"- {register_change[1]} - ({register_change[2]}) - ticket: {register_change[3]}\n"
        
        if message_content_add:
            description += f"Registrar Holds Needed For:\n\n{message_content_add}\n\n"
        if message_content_remove:
            description += f"Removal of Registrar Holds Needed For:\n\n{message_content_remove}\n\n"
        
        if description:
            ticket = self.rm_connection.create_ticket(f"Registrar Hold Changes - {datetime.now().isoformat(sep=' ', timespec='seconds')}",
                                                    self.register_changes_email, self.register_changes_name_first, self.register_changes_name_last,
                                                    '',
                                                    self.rm_connection.statuses['Resolved'], self.rm_connection.project_id)
            self.rm_connection.email_patron(ticket.json()['helpdesk_ticket']['id'], self.rm_connection.statuses['Resolved'], description)
            print(f"Email for registrar changes: {ticket.json()['helpdesk_ticket']['id']}")
    
    # checks that all waived invoices (with a hold) have been properly waived in WCO
    def check_waived_invoices(self):
        invoice_oids = self.db.all("SELECT invoice_oid FROM invoices WHERE hold_status AND waived")
        removed = []
        for invoice_oid in invoice_oids:
            invoice = self.connection.get_invoice(invoice_oid, ['invoiceStatus']).json()['payload']
            if invoice['invoiceStatus'].lower() != 'waived':
                self.remove_hold(invoice_oid)
                removed.append(invoice_oid)
        return removed
    
    # basic moving of end times from invoices to overdues
    def forward_invoice_end_times(self):
        patron_oids = self.db.all('SELECT patron_oid FROM overdues')
        for patron_oid in patron_oids:
            remove_times = self.db.all(f'SELECT hold_remove_time FROM invoices WHERE patron_oid = {patron_oid}')
            if not remove_times:
                remove_times = [None]
            times = [time for time in remove_times if time is not None]
            latest = max(times) if times else None
            if latest == None:
                latest = 'NULL'
            else:
                latest = f"CAST('{latest}' AS TIMESTAMP)"
            self.db.run(f'UPDATE overdues SET hold_remove_time = {latest} WHERE patron_oid = {patron_oid}')
    
    # check for dropped overdues, where a returned checkout doesn't have an end time in db
    # need to add: time offset (only look at checkouts a certain amount of time overdue), >=12 count checker (should have inf hold)
    # add a method for adding idividual checkouts to check returned overdues
    def check_dropped_overdues(self):
        ck_oids = self.db.all('SELECT ck_oid FROM invoices WHERE hold_status AND hold_remove_time IS NULL AND NOT waived AND NOT overdue_lost')
        for ck_oid in ck_oids:
            ck = self.connection.get_allocation(ck_oid, ['allocationState']).json()['payload']
            if ck['allocationState'] == 'CHECKOUT-COMPLETED':
                print(ck['name'], ck_oid)

    # balance invoice and overdues databases
    # reconciling hold_length, hold_remove_time, hold_status, fee_status, and registrar_hold
    # count should always be up to date in overdues
    # def balance_databases(self, patron_oid: int = None):
    #     # balance one patron's info between databases
    #     update_query = ""
    #     if patron_oid:
    #         current_overdue_status = self.db.one("SELECT * FROM overdues WHERE patron_oid = %(oid)i", oid=patron_oid)
    #         current_invoice_status = self.db.all(f"SELECT * FROM invoices WHERE invoice_oid IN ({current_overdue_status.invoice_oids})")

    #         # reconcile hold_length
    #         pass # decide if extending hold length or overlapping

    #         # reconcile hold_remove_time
    #         pass # function of hold_length & current overdues essentially, relies on same decision

    #         # reconcile hold_status
    #         if current_overdue_status.hold_status and True not in (record.hold_status for record in current_invoice_status):
    #             update_query += f"hold_status = {False}, "
    #         elif not current_overdue_status.hold_status and True in (record.hold_status for record in current_invoice_status):
    #             update_query += f"hold_status = {True}, "

    #         # reconcile fee_status
    #         if current_overdue_status.fee_status and True not in (record.fee_status for record in current_invoice_status):
    #             update_query += f"fee_status = {False}, "
    #         elif not current_overdue_status.fee_status and True in (record.fee_status for record in current_invoice_status):
    #             update_query += f"fee_status = {True}, "
            
    #         # reconcile registrar_hold
    #         if current_overdue_status.registrar_hold and True not in (record.registrar_hold for record in current_invoice_status):
    #             update_query += f"registrar_hold = {False}, "
    #         elif not current_overdue_status.registrar_hold and True in (record.registrar_hold for record in current_invoice_status):
    #             update_query += f"registrar_hold = {True}, "
            
    #         self.db.run("UPDATE overdues SET %(query)s WHERE patron_oid = %(oid)i", query=update_query, oid=patron_oid)

    # check for inconsistancies between db and wco
    def reconcile_database(self):
        wco_open_invoices = self.connection.find_invoices(
            query={"and": {"description": "invoice for violation of overdue policies: https://kb.wisc.edu/infolabs/131963", "isHold": True}},
            properties=['payee']).json()['payload']['result']
        db_open_invoices = self.db.all("SELECT patron_oid FROM overdues WHERE hold_status")

        wco_open_invoices_MUTABLE = []
        db_open_invoices_MUTABLE = db_open_invoices.copy()

        for invoice in wco_open_invoices:
            if invoice['payee']['oid'] in db_open_invoices:
                try:
                    db_open_invoices_MUTABLE.remove(invoice['payee']['oid'])
                except ValueError as e:
                    print(f"Patron: {invoice['payee']['name']} has two holds.")
            else:
                wco_open_invoices_MUTABLE.append(invoice['payee']['oid'])
        
        return wco_open_invoices_MUTABLE, db_open_invoices_MUTABLE