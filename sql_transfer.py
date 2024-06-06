from postgres import Postgres
from connection import Connection
from datetime import datetime, timedelta

with open('config.txt', 'r', encoding='utf-8') as in_file:
    for line in in_file:
        if "wco_host" in line.lower():
            wco_host = line.split("=", maxsplit=1)[1].strip()
        elif "wco_user_id" in line.lower():
            wco_userid = line.split("=", maxsplit=1)[1].strip()
        elif "wco_password" in line.lower():
            wco_password = line.split("=", maxsplit=1)[1].strip()
        elif "postgres" in line.lower():
            postgres_pass = line.split("=")[1].strip()

db = Postgres(f"dbname=postgres user=postgres password={postgres_pass}")
wco = Connection(wco_userid, wco_password, wco_host)

db.run("ALTER TABLE overdues RENAME TO overdues_old")
db.run("ALTER TABLE excluded_allocations DROP COLUMN timeout")
db.run("ALTER TABLE excluded_allocations ADD COLUMN processed TIMESTAMP")
db.run("UPDATE excluded_allocations SET processed = 'Now'::TIMESTAMP")

db.run("CREATE EXTENSION IF NOT EXISTS intarray") # required for subracting array of ints from array of ints
db.run("CREATE TABLE IF NOT EXISTS overdues (patron_oid INTEGER PRIMARY KEY, count INTEGER DEFAULT 0, hold_count INTEGER DEFAULT 0, fee_count INTEGER DEFAULT 0, hold_length INTERVAL DEFAULT CAST('0' AS INTERVAL), hold_remove_time TIMESTAMP, invoice_oids INTEGER[], registrar_hold_count INTEGER DEFAULT 0)")
db.run("CREATE TABLE IF NOT EXISTS invoices (invoice_oid INTEGER PRIMARY KEY, count INTEGER DEFAULT 0, hold_status BOOLEAN DEFAULT FALSE, fee_status BOOLEAN DEFAULT FALSE, registrar_hold BOOLEAN DEFAULT FALSE, hold_length INTERVAL DEFAULT CAST('0' AS INTERVAL), overdue_start_time TIMESTAMP, hold_remove_time TIMESTAMP, ck_oid INTEGER, patron_oid INTEGER, waived BOOLEAN DEFAULT FALSE, expiration TIMESTAMP overdue_lost BOOLEAN DEFAULT FALSE)")

for patron_oid, count, hold_status, fee_status, _, hold_remove_time, invoice_oid, registrar_hold in db.all("SELECT * FROM overdues_old"):
    allocs = wco.get_patron_checkouts(patron_oid, ['scheduledEndTime', 'realEndTime']).json()['payload']['result']
    lastest_overdue = None
    for alloc in allocs:
        overdue = False
        r_end = datetime.strptime(alloc['realEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
        sch_end = datetime.strptime(alloc['scheduledEndTime'], '%Y-%m-%dT%H:%M:%S.%f%z')
        if r_end > sch_end and (r_end - sch_end).seconds > 3600:
            overdue = True
        if lastest_overdue == None:
            lastest_overdue = alloc['oid']
        elif lastest_overdue < alloc['oid']:
            lastest_overdue = alloc['oid']
    
    if invoice_oid and hold_remove_time and hold_remove_time > datetime.now():
        hold_len = hold_remove_time - datetime.now() # need to test hold_remove_time - datetime.now() works for interval
        hold_rtime = hold_remove_time
        i_id = str({invoice_oid})
        waived = False
        exp = None
    else:
        # use arbitrary previous invoice with specific expiration date & waived
        invoice_oid = wco.get_patron(patron_oid, ['invoices']).json()['payload']['invoices'][-1]['oid']
        waived = True
        exp = datetime(year=2024, month=6, day=1) + timedelta(days=365*4)

    db.run("INSERT INTO overdues VALUES (%(p_oid)s, %(count)s, %(hold_count)s, %(fee_count)s, %(hold_len)s, %(hold_rtime)s, %(i_id)s, %(reg_hold_count)s)",
            p_oid = patron_oid,
            count = count,
            hold_count = int(hold_status),
            fee_count = int(fee_status),
            hold_len = hold_len,
            hold_rtime = hold_rtime,
            i_id = i_id,
            reg_hold_count = int(registrar_hold))
    db.run("INSERT INTO invoices VALUES (%(i_id)s, %(count)s, %(h_status)s, %(f_status)s, %(reg_hold)s, %(hold_len)s, %(o_stime)s, %(hold_rtime)s, %(ck_id)s, %(p_id)s, %(waived)s, %(exp)s)",
            i_id = invoice_oid,
            count = count,
            h_status = hold_status,
            f_status = fee_status,
            reg_hold = registrar_hold,
            hold_len = hold_len,
            o_stime = f"{datetime.now()}::TIMESTAMP",
            hold_rtime = hold_remove_time,
            ck_id = lastest_overdue,
            p_id = patron_oid,
            waived = waived,
            exp = exp)
    
    # str({invoice_oid}) if invoice_oid else '{}'