from connection import Connection

# For Dos class
import csv
import re
import webbrowser
import pathlib
from datetime import datetime, timezone, timedelta

#####
# Name: dupeCheckouts
# Inputs: None
# Description: Check for duplicate checkouts for a patron across locations
#####
class dupeCheckouts:

    #####
    # Name: check_dupe_types
    # Inputs: alloc_types (json), allocs (list)
    # Output: True/False (bool)
    # Description: 
    #####
    def check_dupe_types(self, current_alloc, prev_allocs: list) -> bool:
        
        # iterate over all types in the current allocation
        for curr_alloc_type in current_alloc['activeTypes']:
            # check this type against other allocations provided in allocs
            for prev_alloc in prev_allocs:

                # only check for laptops and ipads
                #if 'laptop' in curr_alloc_type['name'].lower() or 'ipad' in curr_alloc_type['name'].lower():  # remove line
                
                # If both items are from MERIT, Skip
                if current_alloc['checkoutCenter']['name'] != 'MERIT Library' or  prev_alloc['checkoutCenter']['name'] != 'MERIT Library':
                    
                    # return True for any items that are of the exact same type
                    if curr_alloc_type in prev_alloc['activeTypes']:
                        return True
                    
                    # check parent types
                    # first check that the curr_alloc_type's parent type is one of the parent types from types in prev_alloc
                    # next check if that type is one we care about <-- skip, implement priorities in config later
                    #   Not included Accessories since only wanting to match lower types under that parent type
                    # if both are true, return True
                    if (curr_alloc_type['parent'] in [type_parent['parent'] for type_parent in prev_alloc['activeTypes']]) and \
                        curr_alloc_type['parent'] != "Accessories":
                        return True
                
        return False
    
    #####
    # Name: check_checkouts
    # Inputs: sorted_allocs (list)
    # Output: patron_duplicates (list)
    # Description: Get oid's of all patrons who have duplicate checkouts
    #####
    def check_checkouts(self, sorted_allocs: list) -> list:
        patron_duplicates = []  # hold oids of patrons with duplicate checkouts
        checkouts = []          # temporarily hold checkouts of a single patrons
        patron_oid = -1         # current patrons oid

        # iterate for every checkout
        for alloc in sorted_allocs:
            
            # if oid is different, onto a new patron, process old
            if patron_oid != alloc['patron']['oid']:
                # check for checkouts of same item type for previous patron
                while len(checkouts):
                    # get and remove a checkout from checkouts
                    current = checkouts.pop()

                    # compare current to other (if any) checkouts in checkouts
                    if self.check_dupe_types(current, checkouts):
                        # if the patron has duplicate checkouts add their oid to the list
                        patron_duplicates.append(patron_oid)

            # get the current patrons oid
            patron_oid = alloc['patron']['oid']
            # add the current checkout to the checkouts list
            checkouts.append(alloc)

            # last checkout, process all for this patron
            if alloc == sorted_allocs[-1]:
                # check for checkouts of same item type for previous patron
                while len(checkouts):
                    # get and remove a checkout from checkouts
                    current = checkouts.pop()

                    # compare current to other (if any) checkouts in checkouts
                    if self.check_dupe_types(current, checkouts):
                        # if the patron has duplicate checkouts add their oid to the list
                        patron_duplicates.append(patron_oid)
        
        # return list of patron oids who have duplicate checkouts
        return patron_duplicates
    
    #####
    # Name: get_patrons
    # Inputs: sorted_allocs (list), connection (Connection)
    # Output: patrons (list)
    # Description: Get patron information for those who have duplicate checkouts
    #####
    def get_patrons(self, sorted_allocs: list, connection: Connection) -> list:
        # get oids of patrons with duplicate checkouts
        patron_oids = self.check_checkouts(sorted_allocs)
        patrons = []        # hold patrons informations

        for oid in patron_oids:
            # get patron information from WCO
            patrons.append(connection.get_patron(oid))
        
        return patrons

#####
# Name: Fines
# Inputs: connection (Connection)
# Description: Manage Patrons Fines
#####
class Fines:

    def __init__(self, connection: Connection):
        self.connection = connection

    #####
    # Name: search_open
    # Inputs: None
    # Output: formatted_string (list)
    # Description: Get open invoice information and associated patrons
    #####
    def search_open(self):

        # request invoice information
        invoices = self.connection.get_open_invoices()
        formatted_string = ""       # hold final output string

        # run for each invoice
        for invoice in invoices['payload']['result']:
            # format result with patront and invoice information
            formatted_string += f"Patron: {invoice['person']['name'] if invoice['person']['name'] else 'No name found.'} "\
                                f"({invoice['person']['barcode'] if invoice['person']['barcode'] else 'No barcode found.'})\n" \
                                f"Invoice: {invoice['name']}\n" \
                                f"Outstanding Balance: {invoice['invoiceBalance']}\n" \
                                f"Link: https://uwmadison.webcheckout.net/sso/wco?method=invoice&invoice={invoice['oid']}\n\n"
            
        return formatted_string

#####
# Name: Dos
# Inputs: connection (Connection)
# Description: Manage and perform operations on patrons/checkouts send to the Dean of Students
#####
class Dos:

    def __init__(self, connection: Connection):
        self.connection = connection

    #####
    # Name: check_dos
    # Inputs: None
    # Output: None
    # Description: Finds and outputs those who are submitted to the Dean of Students who no longer need to be (i.e. the returned thier item(s)).
    #              Legacy code from previous Dos script. Will be reworked.
    #####
    def check_dos(self):
        allocations = []

        issue_file = ""

        for file in pathlib.Path('.').glob('*.csv'):
            if 'issues' in file.name.lower() and file.stat().st_ctime > (issue_file.stat().st_ctime if type(issue_file) != str else 0):
                issue_file = file

        if issue_file == "":
            logger.info("Could not find issues file.")

        if issue_file != "":
            with open(issue_file, newline='') as file:
                reader = csv.reader(file)

                for row in reader:
                    if row[1] == 'Stalled' and 'Overdue' in row[4]:
                        match = re.search(r'(CK- *\d+)+', row[7])
                        if (match):
                            for group in match.groups():
                                allocations.append((row[0], group.replace(" ", "")))

            allocations.sort(key=lambda allocation: int(allocation[1][3:]))

            for allocation in allocations.copy():
                
                if self.connection.get_checkout(allocation[1])['payload']['result'][0]['state'] == 'CHECKOUT':
                    allocations.remove(allocation)
                else:
                    logger.info(allocation[1])
            
            if len(allocations):
                in_browser = input("Open redmine tickets? (y/n): ")
                if in_browser.lower()[0] == 'y':
                    for allocation in allocations:
                        webbrowser.open(f"https://redmine.library.wisc.edu/issues/{allocation[0]}")
            else:
                input("No open DoS tickets have been returned. Press enter to exit. ")
        else:
            input("No allocation or issue files found. Press enter to exit. ")
    
    #####
    # Name: get_overdues
    # Inputs: None
    # Output: None
    # Description: Finds and prints checkout information for overdue checkouts. Sorted by Checkout Center.
    #####
    def get_overdues(self):
        tz = datetime.now() - datetime.utcnow()     # get the timezone offset from utc
        time_now = datetime.now(tz=timezone(tz))    # get the current time using found offset
        overdue_amount = 0                          # to hold the total sum of overdues

        # get dictionary of overdues
        overdues = self.connection.get_checkouts_for_overdue()

        # begin output loop
        for location in overdues:
            # ouput current checkout center
            logger.info(">>>>>" + location)
            for checkout in overdues[location]:
                # get the scheduled end time of the checkout and format into an appropriate comparable for time_now
                timestamp = checkout['scheduledEndTime']
                timestamp_formatted = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f%z')

                # check that the checkout is overdue
                if timestamp_formatted < time_now:
                    overdue_amount += 1

                    # Format start_time for output
                    start_time = datetime.strptime(checkout['realStartTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    start_time = start_time.strftime("%m/%d/%Y - %I:%M:%S %p  tz: %z")

                    # output checkout information
                    logger.info(f"Checkout: {checkout['name']}\n" \
                          f"Patron: {checkout['patron']['name']}\n" \
                          f"Item(s): {', '.join(checkout['itemNames'])}\n" \
                          f"Start Time: {start_time}\n" \
                          f"WCO link: https://uwmadison.webcheckout.net/sso/wco?method=show-entity&type=allocation&oid={checkout['oid']}\n\n")
        
        logger.info(f"Total overdue: {overdue_amount}")

    #####
    # Name: get_dos
    # Inputs: None
    # Output: None
    # Description: Gets all patrons submitted to the Dean of Students and related information.
    #              -- In progress
    #####
    def get_dos(self):
        pass

#####
# Name: utils
# Inputs: connection (Connection)
# Description: Manage basic quality of life operations
#####
class utils:

    def __init__(self, connection: Connection):
        self.connection = connection
    
    def search_by_serial(self, filename):
        serials = []
        results = []

        try:
            with open(filename, 'r') as infile:
                serials = infile.read().split()

        except (FileNotFoundError, PermissionError) as err:
            logger.info(err)

        if serials:        
            for response, serial in zip(self.connection.get_items_by_serial(serials), serials):
                items = response['payload']['result']
                if items:
                    out_string = f"Serial: {serial} - {', '.join(item['uniqueId'] + ' ' + item['statusString'] for item in items)}"
                    results.append(out_string)
                else:
                    results.append(f"Serial: {serial} - Not Found")
        
        return results
    
    def get_overdue_consequence(self, allocation, overdue_count: int, end: datetime = None) -> tuple[dict, datetime, dict]:
        if end:
            alloc_end_time = end
        else:
            alloc_end_time = datetime.strptime(allocation['realEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z')

        scheduled_end = datetime.strptime(allocation['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
        tz = timezone(timedelta(hours=-6), name='utc-6')

        length_type_pairs = []
        for item in allocation['items']:
            end_time = datetime.strptime(item['realReturnTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
            overdue_length = end_time - scheduled_end

            # if allocation has a previously returned item that was returned not overdue, it's length would be 0, and no hold should be placed for it
            if overdue_length.days > 0:
                length_type_pairs.append(overdue_length.days, item['rtype'])
        
        if length_type_pairs:
            result = Repercussions(length_type_pairs, overdue_count).update()
        else:
            result = {'Hold': 0, 'Fee': False, 'Registrar Hold': False}

        return result, alloc_end_time, allocation['checkoutCenter']

    def get_overdue_checkout_emails(self, center, start_time, end_time):
        emails = []
        
        checkouts = self.connection.get_new_overdues(center.lower())['payload']['result']
        start_formatted = datetime.strptime(start_time, '%m/%d/%Y')
        end_formatted = datetime.strptime(end_time, '%m/%d/%Y')

        for checkout in checkouts:
            timestamp = checkout['scheduledEndTime'].split('.')[0]
            timestamp_formatted = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')

            if timestamp_formatted > start_formatted and timestamp_formatted < end_formatted:
                emails.append(checkout['patronPreferredEmail'])
        
        logger.info(', '.join(emails))
    
    def get_checkout_emails(self, start_time: datetime):
        emails = {}
        alloc_types = []
        earliest_actual_start = start_time.isoformat()

        checkouts = self.connection.get_allocations(query={"earliestActualStart": earliest_actual_start}, properties=['patronEmail', 'items', 'patron'])['payload']['result']
        
        for checkout in checkouts:
            alloc_types = [alloc_type['rtype']['path'] for alloc_type in checkout['items'] if 'accessories' not in alloc_type['rtype']['path'].lower()]
            if checkout['patronEmail'] not in emails and alloc_types != []:
                emails[checkout['patronEmail']] = [checkout['patron']['name'], alloc_types]
            elif alloc_types != []:
                emails[checkout['patronEmail']][1].extend(alloc_types)
            alloc_types = []
        
        return emails

class Repercussions:

    def __init__(self, length_type_pairs: list[tuple[int, str]], overdue_count: int = None):
        self.resource_type_consequence_mapping = {
            'Accessories': {
                # Up to 1 day
                0: {
                    'Hold': 0,
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 1 day
                1: {
                    'Hold': -1,  # length of overdue
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 10 days
                10: {
                    'Hold': 30,
                    'Fee': True,
                    'Registrar Hold': False
                },
                # More than 20 days
                20: {
                    'Hold': 30,
                    'Fee': True,
                    'Registrar Hold': False
                }
            },
            'Non Accessory': {
                # Up to 1 day
                0: {
                    'Hold': 0,
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 1 day
                1: {
                    'Hold': -1,  # length of overdue
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 10 days
                10: {
                    'Hold': 30,
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 20 days
                20: {
                    'Hold': 30,
                    'Fee': True,
                    'Registrar Hold': True
                }
            },
            'Reserve': {
                # Up to 1 day
                0: {
                    'Hold': 5,
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 1 day
                1: {
                    'Hold': 10,
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 10 days
                10: {
                    'Hold': 30,
                    'Fee': False,
                    'Registrar Hold': False
                },
                # More than 20 days
                20: {
                    'Hold': 30,
                    'Fee': True,
                    'Registrar Hold': True
                }
            },
            'Overdue Count': {
                # at 5, 90 day hold
                5: 90,
                # at 10, 180 day hold
                10: 180,
                # at 12, ban
                12: -2
            }
        }
        self.final_consequences = {
            'Hold': 0,
            'Fee': False,
            'Registrar Hold': False
        }
        self.upper_limits = (0, 1, 10, 20)
        # checks which section of "length of overdue" patron is in - Actual hold length comes from self.resource_type_consequence_mapping with a type
        self.overdue_pairs = [(self._ceil(pair[0]), self._get_bucket(pair[1])) for pair in length_type_pairs]
        self.overdue_count = overdue_count

    def _get(self, idx, length):
        conseq = self.resource_type_consequence_mapping[idx][length]
        # handle 'lenght of overdue' holds
        if conseq['Hold'] == -1:
            conseq['Hold'] = length
        return conseq
    
    def _ceil(self, idx):
        out = 0
        for limit in self.upper_limits:
            if idx >= limit:
                out = limit
        return out
    
    def _get_bucket(self, resource_type):

        if 'reserve' in resource_type['path'].lower() and 'non-reserve' not in resource_type['path'].lower():
            bucket = 'Reserve'
        elif 'accessories' in resource_type['path'].lower():
            bucket = 'Accessories'
        else:
            bucket = 'Non Accessory'
        
        return bucket
    
    def update(self):
        hold_lengths = []
        overdue_count_holds = []

        for overdue_length, resource_type in self.overdue_pairs:
            if self.overdue_count:
                self.overdue_count += 1
                if self.overdue_count in (5, 10, 12):
                    overdue_count_holds.append(self.resource_type_consequence_mapping['Overdue Count'][self.overdue_count])

            hold_lengths.append(self._get(resource_type, overdue_length)['Hold'])

            self.final_consequences['Fee'] = True if self._get(resource_type, overdue_length)['Fee'] or self.final_consequences['Fee'] else False
            self.final_consequences['Registrar Hold'] = True if self._get(resource_type, overdue_length)['Registrar Hold'] or self.final_consequences['Registrar Hold'] else False

        if -2 in overdue_count_holds:
            self.final_consequences['Hold'] = -1
        else:
            for length in overdue_count_holds:
                # sort so lowest length on bottom
                hold_lengths.sort()
                # replace lowest length with special case (if it's higher)
                hold_lengths[0] = max(hold_lengths[0], length)

        self.final_consequences['Hold'] = max(hold_lengths) # items apply holds consecutively

        return self.final_consequences