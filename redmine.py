import requests
import re
from connection import Connection
from datetime import datetime, timezone, timedelta

class RedmineConnection:

    def __init__(self, wco_connection: Connection, host: str, shib_session_cookie_name: str, shib_session_cookie_value: str, redmine_session_cookie: str, redmine_auth_key: str):
        self.wco_connection = wco_connection
        self.host = host
        self.redmine_auth_key = redmine_auth_key

        self.session = requests.Session()

        self.session.cookies.set('_redmine_session', redmine_session_cookie)
        self.session.cookies.set(shib_session_cookie_name, shib_session_cookie_value)

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

                    dos_pos = -1
                    time_ago = None
                    for journal in follow_up_ticket['journals']:
                        dos_pos = journal['notes'].lower().find('dos:')
                        if dos_pos != -1:
                            dos_end_pos = journal['notes'].find('\n', dos_pos)
                            time_ago = datetime.strptime(journal['notes'][dos_pos:dos_end_pos].split()[1], '%m/%d/%Y') - datetime.now()
                    
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
            if computer_lab != 'Unkown Computer Lab':
                out_strings = phone_numbers[computer_lab]
            else:
                out_strings = [f"{obj[0]}: {obj[1]}" for obj in phone_numbers[computer_lab]]

            print(", ".join(out_strings))
            print(f"Total: {len(out_strings)}\n")
    
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
                        phone_numbers.append(f"{checkout['uniqueId']} - {checkout['patron']['name']} - No phone number found")

                    # check for open tickets
                    existing_ticket = self.session.get(url = self.host + f"/search.json?q={checkout['uniqueId']}&scope=my_project", auth=(self.redmine_auth_key, '')).json()

                    if existing_ticket['total_count']:
                        if "overdue" in existing_ticket['results'][0]['title'].lower() and "contact log" in existing_ticket['results'][0]['title'].lower():
                            update_text = f"Due: {timestamp_formatted.strftime('%m/%d/%Y')}\n" \
                                        f"DoS: {time_dos.strftime('%m/%d/%Y')}\n" \
                                        f"Texted {time_now.strftime('%m/%d/%Y')}"

                            # must always go from resolved to new to working on it (redmine doesn't support going from resolved to working on it)
                            self.session.put(url=f'https://redmine.library.wisc.edu/issues/{existing_ticket["results"][0]["id"]}.json',
                                            auth=(self.redmine_auth_key, ''),
                                            json={'issue': {'status_id': 19, 'notes': update_text}})
                            self.session.put(url=f'https://redmine.library.wisc.edu/issues/{existing_ticket["results"][0]["id"]}.json',
                                            auth=(self.redmine_auth_key, ''),
                                            json={'issue': {'status_id': 14}})
                            
                            print(f'Ticket #{existing_ticket["results"][0]["id"]} updated with:\n{update_text}\n')
                            
                            if not phone_number:
                                curr_ticket = self.session.get(url=f'https://redmine.library.wisc.edu/issues/{existing_ticket["results"][0]["id"]}.json',
                                                auth=(self.redmine_auth_key, '')).json()
                                
                                number_pos = curr_ticket['issue']['description'].find('Phone #:')

                                if number_pos != -1:
                                    end_pos = curr_ticket['issue']['description'].find('\n', number_pos)

                                    number = "".join(re.findall('\d+', curr_ticket['issue']['description'][number_pos:end_pos]))
                                    if len(number) == 11:   # remove 1 from +1 if present
                                        number = number[1:]

                                    phone_number = "+1" + number

                                    phone_numbers[-1] = phone_number

                    else:
                        #### FIX so that doesn't include returned part of partially returned allocation in overdue list (subject) [use contents, see tmp.txt]
                        issue_description = (f"{checkout['patron']['name']} - {checkout['patronPreferredEmail']}\n" \
                                                f"Overdue {', '.join(checkout.split(' - ')[-1] for checkout in checkout['itemNames'])} - Contact Log\n" \
                                                f"Item Due {timestamp_formatted.strftime('%m/%d/%Y')}\n\n" \
                                                f"{checkout['uniqueId']}\n\n" \
                                                f"Patron Phone #: {phone_number}\n" \
                                                f"Patron Name: {checkout['patron']['name']}\n\n" \
                                                f"Day 7/Send to DoS ON: {time_dos.strftime('%m/%d/%Y')}\n" \
                                                f"- Texted {time_now.strftime('%m/%d/%Y')}\n\n" \
                                                "----------------------------\n\n")

                        print(issue_description)

        
            phone_numbers.sort()

            print(", ".join(phone_numbers))
            print(f"Total: {len(phone_numbers)}")
