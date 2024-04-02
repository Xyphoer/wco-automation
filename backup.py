from os import system, chdir

response, start = -1, -1
db = None

# hardcoded db address, add configuralable to config later
chdir('C:/Program Files/PostgreSQL/16/bin')
response = system('pg_ctl status -D "C:/Program Files/PostgreSQL/16/data"')
if response != 0: # is not running == 3
    start = system('pg_ctl start -w -D "C:/Program Files/PostgreSQL/16/data"')
    if start != 0: # failed to start
        raise OSError('Failed to connected to database at "C:/Program Files/PostgreSQL/16/data"')

if response == 0 or start == 0:
    backup = system('pg_dump -U postgres > "C:/Users/Public/Downloads/postgres_overdues_db_%DATE:~7,2%-\%DATE:~10,4%_%TIME:~0,2%_%TIME:~3,2%_%TIME:~6,2%.sql"')
    system('timeout 10')