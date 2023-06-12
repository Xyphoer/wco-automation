from connection import Connection
from utils import dupeCheckouts

# get login info
host = "https://uwmadison.webcheckout.net"
userid = input("user id: ")
password = input("password: ")

# create connection
connection = Connection(userid, password, host)

# createa connection to WCO
a = connection.start_session()
print(a)

try:
        print(connection.set_scope())

        # get all currently active checkouts
        checkouts = connection.get_checkouts()

        # create object to check for duplicate checkouts
        dupe_checker = dupeCheckouts()

        # get any patrons who have duplicate items checked out (laptops and ipads only)
        dupe_patrons = dupe_checker.patrons_with_duplicate_checkouts(checkouts, connection)

        # output patron info
        for patron in dupe_patrons:
                patron = patron.json()
                print(f"Name: {patron['payload']['name']}\n" +
                        f"oid: {patron['payload']['oid']}\n" +
                        f"barcode: {patron['payload']['barcode']}\n\n")
finally:
        # always close the open connection before ending
        connection.close()