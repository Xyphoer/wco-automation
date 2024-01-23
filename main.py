from connection import Connection
from redmine import RedmineConnection
from utils import *
from overdues import Overdues
import argparse

# set up argparse
parser = argparse.ArgumentParser(prog = "WCO Automation",
                                 description = "Interacts with WCO to automatically perform " \
                                 "various tasks.",
                                 epilog = "See README for more information.")
parser.add_argument('-dc', '--dupe_checkouts', action = 'store_true',
                    help = "When asserted check for duplicate checkouts across all locations.")
parser.add_argument('-cd', '--check_dos', action = 'store_true',
                    help = 'When asserted check for patrons who have been submitted to DoS who '\
                    'have returerned their overdue item(s).\n' \
                    'Requires an "issues.csv" (or any csv file with "issues" in the name).\n' \
                    '--To get appropriate issues.csv, go to https://redmine.library.wisc.edu/projects/technology-circulation/issues ' \
                    'and export to csv (include the description).')
parser.add_argument('-o', '--overdues', action = 'store_true',
                    help = "When asserted output all patrons with overdue items.")
parser.add_argument('-of', '--open_fines', action = 'store_true',
                    help = "When asserted output all patrons with open fines.")
parser.add_argument('-ss', '--serial_search', action = 'store',
                    help = 'Search for items by serial number. Input must be a text file of serial numbers seprated by newlines.' \
                    'Outputs the corresponding item (if found) and its status.' \
                    'Example usage: main.py -ss in_file.txt')
parser.add_argument('-ru', '--redmine_update', nargs='*',
                    help = 'Updates redmine overdue tickets if they\'ve been returned.' \
                    'Outputs phone numbers for each location and redmine template for ticket creation.' \
                    'Format: start_date end_date centers_to_consider' \
                    'Example usage: main.py -ru mm/dd/yyyy mm/dd/yyyy center1 center2')
parser.add_argument('-ce', '--checkout_emails', nargs=3,
                    help = 'Gets a list of emails for patrons from open checkouts between the two dates for the specified center.' \
                    'Format: start_date end_date center_to_consider' \
                    'Example usage: main.py -ce mm/dd/yyyy mm/dd/yyyy center')
parser.add_argument('po', '--process-overdues', action = 'store_true',
                    help = 'Runs the overdues repercussions script.' \
                    'Example usage: main.py -po')

args = parser.parse_args()

# get login info
wco_host = ''
wco_userid = ''
wco_password = ''
redmine_host = ''
redmine_session_cookie = ''
redmine_auth_key = ''
shibsession_cookie_name = ''
shibsession_cookie_value = ''
project_query_ext = ''

try:
    with open('config.txt', 'r', encoding='utf-8') as in_file:
        for line in in_file:
            if "wco_host" in line.lower():
                wco_host = line.split("=", maxsplit=1)[1].strip()
            elif "wco_user_id" in line.lower():
                wco_userid = line.split("=", maxsplit=1)[1].strip()
            elif "wco_password" in line.lower():
                wco_password = line.split("=", maxsplit=1)[1].strip()
            elif "redmine_host" in line.lower():
                redmine_host = line.split("=", maxsplit=1)[1].strip()
            elif "redmine_session_cookie" in line.lower():
                redmine_session_cookie = line.split("=", maxsplit=1)[1].strip()
            elif "shibsession_cookie_name" in line.lower():
                shibsession_cookie_name = line.split("=", maxsplit=1)[1].strip()
            elif "shibsession_cookie_value" in line.lower():
                shibsession_cookie_value = line.split("=", maxsplit=1)[1].strip()
            elif "redmine_auth_key" in line.lower():
                redmine_auth_key = line.split("=", maxsplit=1)[1].strip()
            elif "project_query_ext" in line.lower():
                project_query_ext = line.split("=", maxsplit=1)[1].strip()
            elif "postgres" in line.lower():
                postgres_pass = line.split("=")[1].strip()
                
except OSError as e:  # file not found or permission error
        wco_host = input("WebCheckout host: ")
        wco_userid = input("WebCheckout user id: ")
        wco_password = input("WebCheckout Password: ")
        redmine_host = input("Redmine host: ")
        redmine_session_cookie = input("redmine_session_cookie: ")
        shibsession_cookie_name = input("_shibsession cookie name: ")
        shibsession_cookie_value = input("_shibsession cookie value: ")

finally:
    if not wco_host:
        wco_host = input("WebCheckout host: ")
    if not wco_userid:
        wco_userid = input("WebCheckout user id: ")
    if not wco_password:
        wco_password = input("WebCheckout password: ")


# create connection
wco_connection = Connection(wco_userid, wco_password, wco_host)

# createa connection to WCO
a = wco_connection.start_session()
print(a)

try:
    print(wco_connection.set_scope())
    if args.dupe_checkouts:
        print("Checking for duplicate checkouts across locations...\n")

        # get all currently active checkouts
        checkouts = wco_connection.get_checkouts()

        # create object to check for duplicate checkouts
        dupe_checker = dupeCheckouts()

        # get any patrons who have duplicate items checked out (laptops and ipads only)
        dupe_patrons = dupe_checker.get_patrons(checkouts, wco_connection)

        # output patron info
        for patron in dupe_patrons:
            patron = patron.json()
            print(f"Name: {patron['payload']['name']}\n" +
                  f"oid: {patron['payload']['oid']}\n" +
                  f"barcode: {patron['payload']['barcode']}\n\n")
        
    if args.open_fines:
        print("Checking for patrons with open fines...\n")

        # create Fines object
        fines = Fines(wco_connection)

        # output results of searching for open fines
        print(fines.search_open())

    if args.check_dos or args.overdues:

        # create DoS object
        dos = Dos(wco_connection)

        if args.check_dos:
            print("Checking for DoS patrons with returned items...\n")

            dos.check_dos()

        if args.overdues:
            print("Checking for overdue checkouts...\n")

            dos.get_overdues()
    
    if args.serial_search:
        print("Performing search by serial numbers...\n")

        utils = utils(wco_connection)

        ss_results_list = utils.search_by_serial(args.serial_search)

        print("\n".join(ss_results_list))
    
    if args.redmine_update:
        print("Performing redmine update...\n")

        if not redmine_host:
            redmine_host = input("redmine host: ")
        if not shibsession_cookie_name:
            wco_userid = input("shibsession cookie name: ")
        if not shibsession_cookie_value:
            wco_password = input("shibsession cookie value: ")
        if not redmine_session_cookie:
            redmine_host = input("redmine session cookie: ")
        if not redmine_auth_key:
            wco_userid = input("redmine auth key: ")
        if not project_query_ext:
            project_query_ext = input("project query ext: ")

        rm_connection = RedmineConnection(wco_connection, redmine_host, shibsession_cookie_name, shibsession_cookie_value, redmine_session_cookie, redmine_auth_key)

        rm_connection.process_working_overdues(project_query_ext=project_query_ext)
        rm_connection.process_new_overdues(start=args.redmine_update[0], end=args.redmine_update[1], centers=args.redmine_update[2:])
    
    if args.checkout_emails:
        print(f"Getting emails for open checkouts from {args.checkout_emails[0]} to {args.checkout_emails[1]} at center: {args.checkout_emails[2]}...\n")

        utils = utils(wco_connection)

        utils.get_checkout_emails(start_time=args.checkout_emails[0], end_time=args.checkout_emails[1], center=args.checkout_emails[2])
    
    if args.process_overdues:
        overdues_start = input("Overdues Start Date (mm/dd/yyyy): ")
        overdues_end = input("Overdues End Date: ")
        print(f"Processing overdues with start date {overdues_start}, end date {overdues_end if overdues_end else 'Now'}...")

        oconn = Overdues(wco_connection, utils(wco_connection), postgres_pass)
        oconn.excluded_allocations(input("Excluded allocations (whitespace seperation): "))
        oconn.update(overdues_start, overdues_end)

finally:
     # always close the open connection before ending
    wco_connection.close()
    print("Closed Connection.")