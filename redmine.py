import requests
import re
from connection import Connection
from datetime import datetime, timezone, timedelta
from postgres import Postgres

class RedmineConnection:

    def __init__(self, wco_connection: Connection, host: str, redmine_auth_key: str):
        self.wco_connection = wco_connection
        self.host = host
        self.redmine_auth_key = redmine_auth_key

        self.session = requests.Session()
        self.session.headers = {'X-Redmine-API-Key': self.redmine_auth_key}

        self.project = self.get_project(name = 'technology-circulation').json()
        self.project_id = self.project['project']['id']
        self.statuses = {'New': self.get_status_id(name = 'New'),
                         'Resolved': self.get_status_id(name = 'Resolved')}
        #self.tracker_support = 3 # hardcoded support tracker (change)
        self.custom_field = {'id': 137, 'name': 'Computer Lab'}

        # self.session.cookies.set('_redmine_session', redmine_session_cookie)
        # self.session.cookies.set(shib_session_cookie_name, shib_session_cookie_value)

    # depricated
    def process_working_overdues(self, project_query_ext):
        response = self.session.get(url=self.host + project_query_ext, auth=(self.redmine_auth_key, ''))

        tz = datetime.now() - datetime.utcnow()     # get the timezone offset from utc
        time_now = datetime.now(tz=timezone(tz))    # get the current time using found offset

        follow_up_text = f"Texted {time_now.strftime('%m/%d/%y')}."
        phone_numbers = {'Unknown Computer Lab': []}

        for issue in response.json()['issues']:
            
            if "overdue" in issue['subject'].lower() and "contact log" in issue['subject'].lower() and "dos" not in issue['subject'].lower():

                regex = re.compile("CK- *\d+")
                checkouts = regex.findall(issue['description'])

                changes = {checkout: {'return': False, 'renew': False} for checkout in checkouts}

                for checkout in checkouts:
                    wco_allocation = self.wco_connection.get_checkout(checkout).json()['payload']['result'][0]

                    timestamp = wco_allocation['endTime']
                    timestamp_formatted = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f%z')

                    if wco_allocation['state'].lower() == 'checkout-completed':
                        changes[checkout]['return'] = True
                    # check if renewed to no longer be late
                    elif timestamp_formatted > time_now:
                        changes[checkout]['renew'] = True
                
                update_text = ""
                for checkout in changes:
                    if changes[checkout]['return']:
                        update_text += f"{checkout} returned {timestamp_formatted.strftime('%m/%d/%Y')}\n"
                    elif changes[checkout]['renew']:
                        update_text += f"{checkout} renewed until {timestamp_formatted.strftime('%m/%d/%Y')}\n"
                
                ## TIDY UP

                x = []
                for y in [value.values() for value in changes.values()]:
                    if True in y:
                        x.append(True)
                    else:
                        x.append(False)

                ## TIDY UP

                if update_text:
                    if False not in x:
                        # resolve
                        self.session.put(url=f'https://redmine.library.wisc.edu/issues/{issue["id"]}.json',
                                        auth=(self.redmine_auth_key, ''),
                                        json={'issue': {'status_id': 10, 'notes': update_text}})
                    else:
                        # update with changes to checkouts (still overdue)
                        self.session.put(url=f'https://redmine.library.wisc.edu/issues/{issue["id"]}.json',
                                        auth=(self.redmine_auth_key, ''),
                                        json={'issue': {'notes': update_text}})
                    print(f"Ticket #{issue['id']} updated with:\n{update_text}\n")
                
                ## follow up texting
                else:
                    follow_up_ticket = self.session.get(url=self.host + f"/issues/{issue['id']}.json?include=journals", auth=(self.redmine_auth_key, '')).json()['issue']

                    time_ago = None
                    content = follow_up_ticket['description'].lower()

                    # add a no send option 
                    # if already texted but still <2 days don't update (need fix) - actually, think this is fine...

                    dos_pos = content.find('dos on:')
                    if dos_pos != -1:
                        dos_end_pos = follow_up_ticket['description'].find('\n', dos_pos)

                    for journal in follow_up_ticket['journals']:
                        if journal['notes']:    # all History counts, not just notes (i.e. can have empty note field, skip these)
                            content = journal['notes'].lower()
                            dos_pos = content.find('dos:')
                            if dos_pos != -1:
                                dos_end_pos = content.find('\n', dos_pos)
                    
                    if dos_pos != -1:
                        time_ago = datetime.strptime(content[dos_pos:dos_end_pos].split()[-1], '%m/%d/%Y') - datetime.now()
                        #print(follow_up_ticket['id'], time_ago)
                    
                    if time_ago and time_ago.days < 2:
                        self.session.put(url=f'https://redmine.library.wisc.edu/issues/{follow_up_ticket["id"]}.json',
                                            auth=(self.redmine_auth_key, ''),
                                            json={'issue': {'notes': follow_up_text}})
                        print(f"Ticket #{follow_up_ticket['id']} updated with:\n{follow_up_text}\n")
                        
                        # get phone number
                        number_pos = follow_up_ticket['description'].find('Phone #:')

                        if number_pos != -1:
                            end_pos = follow_up_ticket['description'].find('\n', number_pos)

                            number = "".join(re.findall('\d+', follow_up_ticket['description'][number_pos:end_pos]))
                            if len(number) == 11:   # remove 1 from +1 if present
                                number = number[1:]

                            phone_number = "+1" + number

                            comp_lab = follow_up_ticket['custom_fields'][0]['value']

                            if comp_lab:
                                try:
                                    phone_numbers[comp_lab].append(phone_number)

                                except KeyError:
                                    phone_numbers[comp_lab] = [phone_number]
                            else:
                                phone_numbers['Unknown Computer Lab'].append((follow_up_ticket['id'], phone_number))
        
        for computer_lab in phone_numbers:
            print(f'-----{computer_lab}-----\n')
            if computer_lab != 'Unknown Computer Lab':
                out_strings = phone_numbers[computer_lab]
            else:
                out_strings = [f"{obj[0]}: {obj[1]}" for obj in phone_numbers[computer_lab]]
                print(out_strings)

            print(", ".join(out_strings))
            print(f"Total: {len(out_strings)}\n")
    
    # depricated
    def process_new_overdues(self, start, end, centers):
        time_now = datetime.now()

        start_formatted = datetime.strptime(start, '%m/%d/%Y')
        end_formatted = datetime.strptime(end, '%m/%d/%Y') + timedelta(hours=23, minutes=59, seconds=59)

        checkouts = {center:self.wco_connection.get_new_overdues(center.lower()).json()['payload']['result'] for center in centers}

        for location in checkouts:
            print(f"---{location}---\n")

            phone_numbers = []
            for checkout in checkouts[location]:
                timestamp = checkout['scheduledEndTime'].split('.')[0]
                timestamp_formatted = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
                time_dos = timestamp_formatted + timedelta(days=7)

                if timestamp_formatted < end_formatted and timestamp_formatted > start_formatted:
                    phone_number = ''

                    if checkout['note']:
                        #phone_numbers.append("+1" + phone.match(allocation['note']).group())
                        phone_number = "+1" + "".join(re.findall('\d+', checkout['note']))
                        phone_numbers.append(phone_number[0:12] if len(phone_number) > 12 else phone_number)
                    else:
                        phone_number = "+1" + "".join(re.findall('\d+', input(f"Phone Number for {checkout['uniqueId']} - {checkout['patron']['name']}: ")))
                        phone_numbers.append(phone_number[0:12] if len(phone_number) > 12 else phone_number)
                        if not phone_number:
                            phone_numbers.append(f"{checkout['uniqueId']} - {checkout['patron']['name']} - No phone number found")

                    # check for open tickets
                    existing_ticket = self.session.get(url = self.host + f"/search.json?q={checkout['uniqueId']}&scope=my_project", auth=(self.redmine_auth_key, '')).json()
                    found = False

                    if existing_ticket['total_count']:
                        for result in existing_ticket['results']:
                            if "overdue" in result['title'].lower() and "contact log" in result['title'].lower():
                                update_text = f"Due: {timestamp_formatted.strftime('%m/%d/%Y')}\n" \
                                            f"DoS: {time_dos.strftime('%m/%d/%Y')}\n" \
                                            f"Texted {time_now.strftime('%m/%d/%Y')}"

                                # must always go from resolved to new to working on it (redmine doesn't support going from resolved to working on it)
                                self.session.put(url=f'https://redmine.library.wisc.edu/issues/{result["id"]}.json',
                                                auth=(self.redmine_auth_key, ''),
                                                json={'issue': {'status_id': 19, 'notes': update_text}})
                                self.session.put(url=f'https://redmine.library.wisc.edu/issues/{result["id"]}.json',
                                                auth=(self.redmine_auth_key, ''),
                                                json={'issue': {'status_id': 14}})
                                
                                print(f'Ticket #{result["id"]} updated with:\n{update_text}\n')
                                
                                if not phone_number:
                                    curr_ticket = self.session.get(url=f'https://redmine.library.wisc.edu/issues/{result["id"]}.json',
                                                    auth=(self.redmine_auth_key, '')).json()
                                    
                                    number_pos = curr_ticket['issue']['description'].find('Phone #:')

                                    if number_pos != -1:
                                        end_pos = curr_ticket['issue']['description'].find('\n', number_pos)

                                        number = "".join(re.findall('\d+', curr_ticket['issue']['description'][number_pos:end_pos]))
                                        if len(number) == 11:   # remove 1 from +1 if present
                                            number = number[1:]

                                        phone_number = "+1" + number

                                        phone_numbers[-1] = phone_number
                                found = True
                                break

                    elif not found:
                        #### FIX so that doesn't include returned part of partially returned allocation in overdue list (subject) [use contents, see tmp.txt]
                        issue_description = (f"{checkout['patron']['name']} - {checkout['patronPreferredEmail']}\n" \
                                                f"Item Due {timestamp_formatted.strftime('%m/%d/%Y')}\n\n" \
                                                f"{checkout['uniqueId']}\n\n" \
                                                f"Patron Phone #: {phone_number}\n" \
                                                f"Patron Name: {checkout['patron']['name']}\n\n" \
                                                f"Day 7/Send to DoS ON: {time_dos.strftime('%m/%d/%Y')}\n" \
                                                f"- Texted {time_now.strftime('%m/%d/%Y')}\n\n")

                        new_ticket = self.session.post(url=f'https://redmine.library.wisc.edu/issues.json',
                                        auth=(self.redmine_auth_key, ''),
                                        json={'issue': {'project_id': self.project_id,
                                                        'status_id': 14, # working on it
                                                        'custom_fields': [{"value": location.title(), "id": self.custom_field['id']}],
                                                        'subject': f"Overdue {', '.join([checkout['resource']['name'] for checkout in checkout['items'] if checkout['realReturnTime'] == None])} - Contact Log\n",
                                                        'description': issue_description}})
                        
                        #print(new_ticket.json())
                        
                        print(f'Ticket #{new_ticket.json()["issue"]["id"]} for {checkout["patron"]["name"]} created.')
                        

                        

        
            phone_numbers.sort()

            print(", ".join(phone_numbers))
            print(f"Total: {len(phone_numbers)}")
    
    def get_project(self, name: str):
        return self.session.get(self.host + f'/projects/{name}.json')

    def get_statuses(self):
        return self.session.get(self.host + '/issue_statuses.json')
    
    def get_status_id(self, name: str):
        statuses = self.get_statuses().json()['issue_statuses']
        for status in statuses:
            if status['name'] == name:
                return status['id']
    
    def get_contact(self, name = '', email = ''):
        if name:
            search = name
        elif email:
            search = email
        else:
            return "name/email must be specified"
        return self.session.get(url = self.host + f'/contacts.json?project_id={self.project_id}&search={search}')

    def create_contact(self, first_name: str, last_name: str, email: str, middle_name: str = ''):
        return self.session.post(url = self.host + '/contacts.json',
                                 json = {"contact": {
                                            "project_id": self.project_id,
                                            "first_name": first_name,
                                            "last_name": last_name,
                                            "email": email,
                                            "visibility": "0" # visible to project only
                                 }})

    # no email sent to contact
    def create_ticket(self, subject: str, contact_email, contact_first_name: str = '', contact_last_name: str = '', description: str = '', status_id: int = None, project_id: int = None):
        return self.session.post(url = self.host + '/helpdesk_tickets.json',
                                 json = {"helpdesk_ticket": {
                                            "issue": {
                                                "project_id": project_id if project_id else self.project_id,
                                                "status_id": status_id if status_id else self.statuses['Resolved'],
                                                "description": description,
                                                "subject": subject
                                                },
                                            "contact": {
                                                "first_name": contact_first_name,
                                                "last_name": contact_last_name,
                                                "email": contact_email
                                         }}})

    def email_patron(self, issue_id: int, status_id: int, content: str):
        return self.session.post(url = self.host + '/helpdesk/email_note.json',
                                 json = {"message": {
                                            "issue_id": issue_id,
                                            "status_id": status_id,
                                            "content": content
                                 }})

class Texting(RedmineConnection):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location_checkout_pairs = {}
        self.location_options = self.wco_connection.centers.keys()

    def add_checkout(self, location, checkout):
        try:
            self.location_checkout_pairs[location.lower()].append(checkout)
        except KeyError as e:
            self.location_checkout_pairs[location.lower()] = [checkout]

    # sketchy
    def ticketify(self):
        time_now = datetime.now()
        for center in self.location_checkout_pairs:

            ##### temporary blocker for not processing InfoLabs who haven't asked for texting
            if center not in ('college library', 'memorial library'):
                continue

            print(f"---{center}---\n")

            phone_numbers = []
            for checkout in self.location_checkout_pairs[center]:
                timestamp = checkout['scheduledEndTime'].split('.')[0]
                timestamp_formatted = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
                phone_number = ''

                if checkout['note']:
                    #phone_numbers.append("+1" + phone.match(allocation['note']).group())
                    phone_number = "+1" + "".join(re.findall('\d+', checkout['note']))
                    phone_numbers.append(phone_number[0:12] if len(phone_number) > 12 else phone_number)
                else:
                    phone_number = "+1" + "".join(re.findall('\d+', input(f"Phone Number for {checkout['uniqueId']} - {checkout['patron']['name']}: ")))
                    phone_numbers.append(phone_number[0:12] if len(phone_number) > 12 else phone_number)
                    if not phone_number:
                        phone_numbers.append(f"{checkout['uniqueId']} - {checkout['patron']['name']} - No phone number found")

                # check for open tickets
                existing_ticket = self.session.get(url = self.host + f"/search.json?q={checkout['uniqueId']}&scope=my_project").json()
                found = False

                if existing_ticket['total_count']:
                    for result in existing_ticket['results']:
                        if "overdue" in result['title'].lower() and "contact log" in result['title'].lower():
                            update_text = f"Due: {timestamp_formatted.strftime('%m/%d/%Y')}\n" \
                                        f"Texted {time_now.strftime('%m/%d/%Y')}"

                            ## Stay as resolved
                            # must always go from resolved to new to working on it (redmine doesn't support going from resolved to working on it)
                            # self.session.put(url=f'https://redmine.library.wisc.edu/issues/{result["id"]}.json',
                            #                 auth=(self.redmine_auth_key, ''),
                            #                 json={'issue': {'status_id': 19, 'notes': update_text}})
                            # self.session.put(url=f'https://redmine.library.wisc.edu/issues/{result["id"]}.json',
                            #                 auth=(self.redmine_auth_key, ''),
                            #                 json={'issue': {'status_id': 14}})
                            
                            print(f'Ticket #{result["id"]} updated with:\n{update_text}\n')
                            
                            if not phone_number:
                                curr_ticket = self.session.get(url=f'https://redmine.library.wisc.edu/issues/{result["id"]}.json').json()
                                
                                number_pos = curr_ticket['issue']['description'].find('Phone #:')

                                if number_pos != -1:
                                    end_pos = curr_ticket['issue']['description'].find('\n', number_pos)

                                    number = "".join(re.findall('\d+', curr_ticket['issue']['description'][number_pos:end_pos]))
                                    if len(number) == 11:   # remove 1 from +1 if present
                                        number = number[1:]

                                    phone_number = "+1" + number

                                    phone_numbers[-1] = phone_number
                            found = True
                            break

                if not found:
                    #### FIX so that doesn't include returned part of partially returned allocation in overdue list (subject) [use contents, see tmp.txt]
                    issue_description = (f"{checkout['patron']['name']} - {checkout['patronPreferredEmail']}\n" \
                                            f"Item Due {timestamp_formatted.strftime('%m/%d/%Y')}\n\n" \
                                            f"{checkout['uniqueId']}\n\n" \
                                            f"Patron Phone #: {phone_number}\n" \
                                            f"Patron Name: {checkout['patron']['name']}\n\n" \
                                            f"- Texted {time_now.strftime('%m/%d/%Y')}\n\n")

                    overdue_items = [item['resource']['name'] for item in checkout['items'] if item['state'] == 'CHECKOUT']
                    new_ticket = self.create_ticket(subject=f"Overdue {', '.join(overdue_items)} - Contact Log\n", contact_email=checkout['patronPreferredEmail'], description=issue_description, project_id=self.project_id)
                    # new_ticket = self.session.post(url=f'https://redmine.library.wisc.edu/issues.json',
                    #                 json={'issue': {'project_id': self.project_id,
                    #                                 'status_id': 10, # resolved
                    #                                 'custom_fields': [{"value": center.title(), "id": self.custom_field['id']}],
                    #                                 'subject': f"Overdue {', '.join(overdue_items)} - Contact Log\n",
                    #                                 'description': issue_description}})
                    
                    #print(new_ticket.json())
                    
                    print(f'Ticket #{new_ticket.json()["helpdesk_ticket"]["id"]} for {checkout["patron"]["name"]} created.')
        
            phone_numbers.sort()

            print(", ".join(phone_numbers))
            print(f"Total: {len(phone_numbers)}")


# possibly explore better methods
class CannedMessages:
    def __init__(self, invoice_oid: int, wco_connection: Connection, db: Postgres, settled: str = None):

        self.db = db
        self.invoice_oid = invoice_oid
        self.wco_conn = wco_connection
        self.settled = settled

        self.canned_registrar_placed = {'subject': 'Registrar Hold Placed',
                                         'description': 'Hello,\n\n' \
                                                        'Due to the length of your overdue, a registrar hold has been placed on your account.\n' \
                                                        'For more details on our overdue policy please see our KB documentation (https://kb.wisc.edu/infolabs/131963).\n' \
                                                        'Once the overdue equipment has been returned, within a few business days the hold will be removed.\n\n' \
                                                        'Please let us know if you have any further questions or concerns.\n\n' \
                                                        'Best,'}
        self.canned_registrar_removed = {'subject': 'Registrar Hold Removed',
                                         'description': 'Hello,\n\n' \
                                                        'Due to the return of your overdue equipment, the registrar hold will be removed within the next few business days.\n' \
                                                        'For more details on why this hold was placed, please see our overdue policy documentation (https://kb.wisc.edu/infolabs/131963).\n\n' \
                                                        'Please let us know if you have any further questions or concerns.\n\n' \
                                                        'Best,'}

    def _get_checkout_info(self, invoice_oid: int):
        ck_oid, patron_oid = self.db.one('SELECT ck_oid, patron_oid FROM invoices WHERE invoice_oid = %(i_oid)s', i_oid = invoice_oid)
        allocation = self.wco_conn.get_allocation(ck_oid, ['items', 'patron', 'scheduledEndTime', 'checkoutCenter', 'realEndTime', 'uniqueId']).json()['payload']
        count = self.db.one('SELECT count FROM overdues WHERE patron_oid = %(p_oid)s', p_oid=patron_oid)
        invoice = self.wco_conn.get_invoice(invoice_oid).json()['payload']
        invoice_lines = self.wco_conn.get_invoice_lines(invoice).json()['payload']['result']

        classifications = []
        item_name = []
        charge = 0

        for item in allocation['items']:
            classifications.append(item['rtype']['path'])
            item_name.append(item['resource']['name'])
        
        amount = 0
        for invoice_line in invoice_lines:
            charge += invoice_line['amount'] / 100

        returned_date = datetime.strptime(allocation['realEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z').isoformat(sep=' ', timespec='seconds') if allocation['realEndTime'] else None
        
        return (allocation['patron']['name'], allocation['checkoutCenter']['name'], allocation['uniqueId'],
                datetime.strptime(allocation['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z').isoformat(sep=' ', timespec='seconds'),
                count, item_name, classifications, invoice['name'], charge, self.settled if self.settled else returned_date)

    def get_base(self):
        patron_name, checkout_center, ck_id, due_date, count, item_names, classifications, invoice_id, _, _ = self._get_checkout_info(self.invoice_oid)

        self._base_item_list = '\n'.join([f'- {item_name} - {classification}\n' for item_name, classification in zip(item_names, classifications)])
        return {'subject': f"{patron_name} - Overdue - {ck_id} - {invoice_id}",
                     'description':
                        f"Hello {patron_name}\n\n" \
                        f"Your Checkout {ck_id} from {checkout_center} InfoLab was due back {due_date}.\n" \
                        "As such, a hold has been placed on your WebCheckout account in regards to the overdue policy (https://kb.wisc.edu/library/131963) for the following items:\n\n" \
                        f"{self._base_item_list}\n" \
                        f"Please note that your historical overdue item count is: {count}\n\n" \
                        "Please return or contact us as soon as possible. For any questions or concerns please feel free to reply " \
                        f"or reach out to us at technologycirculation@library.wisc.edu or in person at the {checkout_center} InfoLab.\n\n" \
                        "Best,"}

    def get_charge(self):
        patron_name, checkout_center, ck_id, due_date, count, item_names, classifications, invoice_id, charge, _ = self._get_checkout_info(self.invoice_oid)

        self._charge_item_list = '\n'.join([f'- {item_name} - {classification}\n' for item_name, classification in zip(item_names, classifications)])
        return {'subject': f"{patron_name} - Overdue Charge - {ck_id} - {invoice_id}",
                       'description':
                            f"Hello {patron_name}\n\n" \
                            f"Your checkout {ck_id} from {checkout_center} InfoLab was due back {due_date}.\n" \
                            "As such, a hold has been placed on your WebCheckout account in regards to the overdue policy (https://kb.wisc.edu/library/131963) for the following items:\n\n" \
                            f"{self._charge_item_list}\n" \
                            f"Total Charge: {charge}\n" \
                            f"Please note that your historical overdue item count is: {count}\n\n" \
                            f"To resolve this invoice, either return the overdue items to {checkout_center} InfoLab, " \
                            "or pay the total amount at College Library InfoLab (2nd floor computer lab in College Library).\n\n" \
                            "For any questions or concerns please feel free to reply " \
                            f"or reach out to us at technologycirculation@library.wisc.edu or in person at the {checkout_center} InfoLab.\n\n" \
                            "Best,"}
    
    def get_returned(self):
        patron_name, checkout_center, ck_id, _, count, item_names, classifications, invoice_id, _, return_date = self._get_checkout_info(self.invoice_oid)
        hold_length, removal_date = self.db.one("SELECT hold_length, hold_remove_time FROM invoices WHERE invoice_oid = %(i_oid)s", i_oid=self.invoice_oid)
        # make nicer methodology
        if not return_date:
            return False

        self._base_item_list = '\n'.join([f'- {item_name} - {classification}\n' for item_name, classification in zip(item_names, classifications)])
        return {'subject': f"{patron_name} - Overdue Return - {ck_id} - {invoice_id}",
                         'description':
                            f"Hello {patron_name}\n\n" \
                            f"Your overdue checkout {ck_id} from {checkout_center} InfoLab has been resolved on {return_date}.\n" \
                            f"As such, any fee or register hold will be removed within a few business days. " \
                            f"A WebCheckout hold on your account will remain in effect for {hold_length.days} days after the return in accordance to the overdue policy " \
                            "(https://kb.wisc.edu/library/131963) for the following items:\n\n" \
                            f"{self._base_item_list}\n" \
                            f"Final WebCheckout Hold Removal Date: {removal_date.isoformat(sep=' ', timespec='seconds')}\n" \
                            f"Please note that your historical overdue item count is: {count}\n\n" \
                            "For any questions or concerns please feel free to reply " \
                            f"or reach out to us at technologycirculation@library.wisc.edu or in person at the {checkout_center} InfoLab.\n\n" \
                            "Best,"}
    
    def get_lifted(self):
        patron_name, checkout_center, ck_id, _, count, _, _, invoice_id, _, _ = self._get_checkout_info(self.invoice_oid)
        removal_date = self.db.one("SELECT hold_remove_time FROM invoices WHERE invoice_oid = %(i_oid)s", i_oid=self.invoice_oid)
        if not removal_date:
            removal_date = datetime.now()

        return {'subject': f"{patron_name} - Overdue Lifted - {ck_id} - {invoice_id}",
                       'description':
                            f"Hello {patron_name}\n\n" \
                            f"The WebCheckout hold for overdue {ck_id} from {checkout_center} InfoLab has been lifted on {removal_date.isoformat(sep=' ', timespec='seconds')}.\n" \
                            "As such, in accordance with our overdue policy (https://kb.wisc.edu/library/131963), you are now eligible to check out equipment " \
                            "from any Infolab location provided there are no additional holds on your account.\n\n" \
                            f"Please note that your historical overdue item count is: {count}\n\n" \
                            "For any questions or concerns please feel free to reply " \
                            f"or reach out to us at technologycirculation@library.wisc.edu or in person at the {checkout_center} InfoLab.\n\n" \
                            "Best,"}
    
    def get_lost(self):
        patron_name, checkout_center, ck_id, due_date, count, item_names, classifications, invoice_id, charge, _ = self._get_checkout_info(self.invoice_oid)

        self._lost_item_list = '\n'.join([f'- {item_name} - {classification}\n' for item_name, classification in zip(item_names, classifications)])

        return {'subject': f"{patron_name} - Declared Lost - {ck_id} - {invoice_id}",
                'description':
                    f"Hello {patron_name}\n\n" \
                    f"Your checkout {ck_id} from {checkout_center} InfoLab has been declared lost on {datetime.now().strftime('%m/%d/%Y')}.\n" \
                    "You will have received a return email notice as we believe the item has been lost. " \
                    "As such a replacement fee will remain on your WebCheckout account until the item has been returned or the fee paid.\n\n" \
                    "Additionally, a registrar hold and WebCheckout hold will remain in effect until return or payment.\n" \
                    f"Please refer to our overdue policy (https://kb.wisc.edu/library/131963) for more information.\n\n" \
                    f"{self._lost_item_list}\n" \
                    f"Total Charge: {charge}\n" \
                    f"Please note that your historical overdue item count is: {count}\n\n" \
                    f"To resolve this invoice, either return the overdue items to {checkout_center} InfoLab, " \
                    "or pay the total amount at College Library InfoLab (2nd floor computer lab in College Library).\n\n" \
                    "For any questions or concerns please feel free to reply " \
                    f"or reach out to us at technologycirculation@library.wisc.edu or in person at the {checkout_center} InfoLab.\n\n" \
                    "Best,"}