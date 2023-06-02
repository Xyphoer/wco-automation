from connection import Connection
from utils import Utils

host = "https://uwmadison.webcheckout.net"
userid = input("user id: ")
password = input("password: ")

connection = Connection(userid, password, host)

print(connection.startSession())

try:
        print(connection.setScope())

        checkouts = connection.getCheckouts()

        dupe_checker = Utils.dupeCheckouts()

        dupe_patrons = dupe_checker.patrons_with_duplicate_checkouts(checkouts, connection)

        for patron in dupe_patrons:
                patron = patron.json()
                print(f"Name: {patron['payload']['name']}\n" +
                        f"oid: {patron['payload']['oid']}\n" +
                        f"barcode: {patron['payload']['barcode']}\n\n")
finally:
        connection.close()