from connection import Connection
from redmine import RedmineConnection, Texting
from utils import *
from overdues import Overdues
import argparse
from datetime import datetime
import logging
import logging.config
from os import path, mkdir

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
parser.add_argument('-po', '--process-overdues', action = 'store_true',
                    help = 'Runs the overdues repercussions script.' \
                    'Example usage: main.py -po')
parser.add_argument('-log', '--log-level', type=int, choices=range(5), default=4,
                    help="""Details how much info should be displayed. The higher, the more info.
                    Each number includes everything from the numbers prior.
                    0: No info  1: Critical Errors  2: Errors  3: Warnings  4: Info  5: Debug""")

args = parser.parse_args()

log_dict = {0: 'NOTSET', 1: 'CRITICAL', 2: 'ERROR',  3: 'WARNING', 4: 'INFO', 5: 'DEBUG'}

logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'basic': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': log_dict[args.log_level],
            'formatter': 'basic',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.FileHandler',
            'level': 'DEBUG',
            'formatter': 'basic',
            'filename': f'../logs/wco_automation[{datetime.now().strftime("%Y-%m-%d")}].log'
        }
    },
    #  Alternate method of declaring root (higher priority)
    # 'root': {
    #     'level': 'NOTSET',
    #     'handlers': ['console', 'file']
    # },
    'loggers': {
        '': { # root
            'level': 'NOTSET',
            'handlers': ['console', 'file']
        },
        'overdues': {
            'level': 'DEBUG'
        },
        'decorators': {
            'level': 'DEBUG'
        },
        'redmine': {
            'level': 'DEBUG'
        }
    }
})

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

# # file handler for all messages
# if not path.exists('../logs'):
#     mkdir('../logs')
# fh = logging.FileHandler(f'../logs/wco_automation[{datetime.now().strftime("%Y-%m-%d")}].log')
# fh.setLevel(logging.DEBUG)

# # console handler for user desired messages
# sh = logging.StreamHandler()
# sh.setLevel(log_dict[args.log_level])

# # basic readable formatter for both outputs
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# fh.setFormatter(formatter)
# sh.setFormatter(formatter)

# # attach handlers to logger
# logger.addHandler(fh)
# logger.addHandler(sh)

# get login info
wco_host = ''
wco_userid = ''
wco_password = ''
redmine_host = ''
redmine_auth_key = ''
project_query_ext = ''
postgres_pass = ''

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

finally:
    if not wco_host:
        wco_host = input("WebCheckout host: ")
    if not wco_userid:
        wco_userid = input("WebCheckout user id: ")
    if not wco_password:
        wco_password = input("WebCheckout password: ")
    if not redmine_host:
        redmine_host = input("redmine host: ")
    if not redmine_auth_key:
        redmine_auth_key = input("redmine auth key: ")
    if not project_query_ext:
        project_query_ext = input("project query ext: ")
    if not postgres_pass:
        postgres_pass = input("postgres password: ")


# create connection
wco_connection = Connection(wco_userid, wco_password, wco_host)

try:
    if args.dupe_checkouts:
        logger.info("Checking for duplicate checkouts across locations...\n")

        # get all currently active checkouts
        checkouts = wco_connection.get_checkouts()

        # create object to check for duplicate checkouts
        dupe_checker = dupeCheckouts()

        # get any patrons who have duplicate items checked out (laptops and ipads only)
        dupe_patrons = dupe_checker.get_patrons(checkouts, wco_connection)

        # output patron info
        for patron in dupe_patrons:
            logger.info(f"Name: {patron['payload']['name']}\n" +
                  f"oid: {patron['payload']['oid']}\n" +
                  f"barcode: {patron['payload']['barcode']}\n\n")
        
    if args.open_fines:
        logger.info("Checking for patrons with open fines...\n")

        # create Fines object
        fines = Fines(wco_connection)

        # output results of searching for open fines
        logger.info(fines.search_open())

    if args.check_dos or args.overdues:

        # create DoS object
        dos = Dos(wco_connection)

        if args.check_dos:
            logger.info("Checking for DoS patrons with returned items...\n")

            dos.check_dos()

        if args.overdues:
            logger.info("Checking for overdue checkouts...\n")

            dos.get_overdues()
    
    if args.serial_search:
        logger.info("Performing search by serial numbers...\n")

        utils = utils(wco_connection)

        ss_results_list = utils.search_by_serial(args.serial_search)

        logger.info("\n".join(ss_results_list))
    
    # depricated
    if args.redmine_update:
        pass # depricated - to remove/rework
        # print("Performing redmine update...\n")

        # if not redmine_host:
        #     redmine_host = input("redmine host: ")
        # if not shibsession_cookie_name:
        #     wco_userid = input("shibsession cookie name: ")
        # if not shibsession_cookie_value:
        #     wco_password = input("shibsession cookie value: ")
        # if not redmine_session_cookie:
        #     redmine_host = input("redmine session cookie: ")
        # if not redmine_auth_key:
        #     wco_userid = input("redmine auth key: ")
        # if not project_query_ext:
        #     project_query_ext = input("project query ext: ")

        # rm_connection = RedmineConnection(wco_connection, redmine_host, shibsession_cookie_name, shibsession_cookie_value, redmine_session_cookie, redmine_auth_key)

        # rm_connection.process_working_overdues(project_query_ext=project_query_ext)
        # rm_connection.process_new_overdues(start=args.redmine_update[0], end=args.redmine_update[1], centers=args.redmine_update[2:])
    
    if args.checkout_emails:
        logger.info(f"Getting emails for open checkouts from {args.checkout_emails[0]} to {args.checkout_emails[1]} at center: {args.checkout_emails[2]}...\n")

        utils = utils(wco_connection)

        utils.get_overdue_checkout_emails(start_time=args.checkout_emails[0], end_time=args.checkout_emails[1], center=args.checkout_emails[2])
    
    if args.process_overdues:
        overdues_correct_date_range = ''
        texting = Texting(wco_connection, redmine_host, redmine_auth_key)
        redmine_conn = RedmineConnection(wco_connection, redmine_host, redmine_auth_key)
        oconn = Overdues(wco_connection, utils(wco_connection), redmine_conn, texting, postgres_pass)
        # oconn.check_waived_invoices()
        while overdues_correct_date_range.lower()[:1] != 'y':
            overdues_start = input("Overdues Start Date (mm/dd/yyyy): ")
            overdues_start_dt = datetime.strptime(overdues_start, '%m/%d/%Y') if '/' in overdues_start else oconn.last_run()
            logger.debug(f'overdues_start time: {overdues_start_dt.isoformat()}')

            overdues_end = input("Overdues End Date: ")
            overdues_end_dt = datetime.strptime(overdues_end, '%m/%d/%Y') if '/' in overdues_end else datetime.now()
            logger.debug(f'overdues_end time: {overdues_end_dt.isoformat()}')

            overdues_start_end_diff = overdues_end_dt - overdues_start_dt
            overdues_correct_date_range = input(f"Start Date of {overdues_start_dt.isoformat(sep=' ', timespec='seconds')} is " \
                                                f"{overdues_start_end_diff.days} days, {overdues_start_end_diff.seconds // 3600} hours from end time of " \
                                                f"{overdues_end_dt.isoformat(sep=' ', timespec='seconds')}. Is this correct? [y/n]: ")
        
        logger.info(f"Processing overdues with start date {overdues_start_dt.isoformat(sep=' ', timespec='seconds')}, end date {overdues_start_dt.isoformat(sep=' ', timespec='seconds')}...")

        permanent_excluded_cks = input("Permanent Excluded allocations (whitespace seperation): ")
        logger.debug('Processing permanent excluded allocations with input: ' + permanent_excluded_cks)
        oconn.excluded_allocations(permanent_excluded_cks)

        temporary_excluded_cks = input("Temporary Excluded allocations (whitespace seperation): ")
        logger.debug('Processing temporary excluded allocations with input: ' + temporary_excluded_cks)
        oconn.excluded_allocations(temporary_excluded_cks, temporary=True)

        oconn.update(overdues_start_dt, overdues_end_dt)

finally:
     # always close the open connection before ending
    wco_connection.close()
    logger.info("Closed Connection.")