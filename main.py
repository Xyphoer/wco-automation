from connection import Connection
from utils import dupeCheckouts, Fines, Dos
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

args = parser.parse_args()

# get login info
wco_host = ''
wco_userid = ''
wco_password = ''

try:
    with open('config.txt', 'r', encoding='utf-8') as in_file:
        for line in in_file:
            if "wco_host" in line.lower():
                wco_host = line.split("=")[1].strip()
            if "wco_user_id" in line.lower():
                wco_userid = line.split("=")[1].strip()
            if "wco_password" in line.lower():
                wco_password = line.split("=")[1].strip()
                
except FileNotFoundError as e:  #OSError (all) - or need Permission error
        wco_host = input("WebCheckout host: ")
        wco_userid = input("WebCheckout user id: ")
        wco_password = input("WebCheckout Password: ")

finally:
    if not wco_host:
        wco_host = input("WebCheckout host: ")
    if not wco_userid:
        wco_userid = input("WebCheckout user id: ")
    if not wco_password:
        wco_password = line.split("=")[1].strip()


# create connection
connection = Connection(wco_userid, wco_password, wco_host)

# createa connection to WCO
a = connection.start_session()
print(a)

try:
    print(connection.set_scope())
    if args.dupe_checkouts:
        print("Checking for duplicate checkouts across locations...\n")

        # get all currently active checkouts
        checkouts = connection.get_checkouts()

        # create object to check for duplicate checkouts
        dupe_checker = dupeCheckouts()

        # get any patrons who have duplicate items checked out (laptops and ipads only)
        dupe_patrons = dupe_checker.get_patrons(checkouts, connection)

        # output patron info
        for patron in dupe_patrons:
            patron = patron.json()
            print(f"Name: {patron['payload']['name']}\n" +
                  f"oid: {patron['payload']['oid']}\n" +
                  f"barcode: {patron['payload']['barcode']}\n\n")
        
        if args.open_fines:
            print("Checking for patrons with open fines...\n")

            # create Fines object
            fines = Fines(connection)

            # output results of searching for open fines
            print(fines.search_open())

        if args.check_dos or args.overdues:

            # create DoS object
            dos = Dos(connection)

            if args.check_dos:
                print("Checking for DoS patrons with returned items...\n")

                dos.check_dos()

                if args.overdues:
                    print("Checking for overdue checkouts...\n")

                    dos.get_overdues()

finally:
     # always close the open connection before ending
    connection.close()
    print("Closed Connection.")