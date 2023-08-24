# InfoLab WebCheckout Automatic Helper
Program for automatic interfacing with [WebCheckouts api](https://api.webcheckout.net).
The program's primary purpose is to automate common, procedural tasks with relation to WebCheckout, as well as perform more complicated searches that are difficult to perform manually.

## Details:

### Current capabilities:
- Checking for duplicate resource type checkouts at different checkout centers.
- Checking for open invoices.
- Getting overdue item information
- Checking for returned items on DoS checkouts.

## Usage:
`main.py [OPTIONS]`

### OPTIONS:
```
-dc, --dupe_checkouts           Searches for duplicate checkouts across all locations.
                                Respects MERITs policies.
-cd, --check_dos                Checks for items returned from checkouts that have been
                                submitted to the Dean of Students.
                                This requires an "issues.csv" file
                                (any csv file with "issues" in the name is sufficient).
                                To get this file, navigate to
                                https://redmine.library.wisc.edu/projects/technology-circulation/issues
                                and click the csv button in the bottom right to download a csv file.
                                Include the description or the program will not work correctly.
                                Download the csv file to the same directory as "main.py"
-o, -overdues                   Lists information relating to patrons who are currently overdue.
                                Information includes: overdue location, checkout id, patron name,
                                checkout item(s), checkout start time, and WCO link to allocation.
-of, --open_fines               Outputs information of patrons with open fines. Information includes:
                                patron name & id number, invoice number, outstanding balance, and WCO link to invoice.
```

### CONFIG:
This program supports a config file with the following format:

```
wco_host=https://url.to.host
wco_user_id=user
wco_password=password
```

If the information is not able to be found in the config file, the program will prompt you directly.

## Support
Developer: Elias Cassis

Area: Internal Tools