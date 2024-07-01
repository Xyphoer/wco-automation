# InfoLab WebCheckout/Redmine Automatic Helper
Program for automatic interfacing with [WebCheckouts api](https://api.webcheckout.net) as well as [Redmines api](https://www.redmine.org/projects/redmine/wiki/Rest_api) and [RedmineUP api](https://www.redmineup.com/pages/help/developers).

The program's primary purpose is to automate common, procedural tasks with relation to WebCheckout, as well as perform more complicated searches that are difficult to perform manually.

# Details:

### Current capabilities:
- Automatic processing of overdue checkouts across all InfoLabs according to [policy](https://kb.wisc.edu/library/131963).
- Checking for duplicate resource type checkouts at different checkout centers.
- Checking for open invoices.
- Getting overdue item information.
- Some other capabilities are depricated.

# Usage:
`main.py [OPTIONS]`

## OPTIONS:
```
-po, --process_overdues         processes overdues according to overdue policy. More details in dedicated section.
-dc, --dupe_checkouts           Searches for duplicate checkouts across all locations.
                                Respects MERITs policies.
-o, -overdues                   Lists information relating to patrons who are currently overdue.
                                Information includes: overdue location, checkout id, patron name,
                                checkout item(s), checkout start time, and WCO link to allocation.
-of, --open_fines               Outputs information of patrons with open fines. Information includes:
                                patron name & id number, invoice number, outstanding balance, and WCO link to invoice.
-ss, --serial_search            Search for items by serial number. Input must be a text file of serial numbers seprated by newlines.
                                Outputs the corresponding item (if found) and its status.
                                Example usage: main.py -ss in_file.txt
-ce, --checkout_emails          Gets a list of emails for patrons from open checkouts between the two dates for the specified center.
                                Format: start_date end_date center_to_consider
                                Example usage: main.py -ce mm/dd/yyyy mm/dd/yyyy center
```

### process_overdues
Automated system paired the InfoLabs [overdue policy](https://kb.wisc.edu/library/131963).

Automatically places/removes WebCheckout invoice holds and charges, emails patrons though redmines, provides phone numbers to text, and refers patron who require registrar holds.\
Additionally processes overdues items past 6 months as lost by returning and deleting the items in WebCheckout, contacting the patron, and maintaining a WebCheckout invoice and registrar hold.

#### Steps:
Intermediate steps where interaction will be requested from the user.
- Overdue start and end dates. Must be in `mm/dd/yyyy` format.
    - Used to determine what time range to look at returned overdues for. If not specified, will use the start date as the time of last run of `process_overdues` and
      end date of the current time.
    - Strongly recommended to not specify any date range as it is almost always unnecessary and may cause inconsistances later. This feature will eventually be re-worked.
- Excluded Allocations. Must be a positive integer or a positive integer preceded with `CK-`
    - Specifies any specific checkouts to be excluded from the overdue policy. Any already incurred repercussions will be removed.
- Phone Numbers. Must be a 10 digit number.
    - If a phone number is not automatically found, it is required to be input. Automatic fallback to the UW directory will be implemented in a future update.
- Returned lost allocations. Must be a positive integer or a positive integer preceded with `CK-`
    - Specifies any specific checkouts previously declared lost by the program that have been returned.

## CONFIG:
This program supports a `config.txt` file with the following format:

```
wco_host=https://url.to.host
wco_user_id=user
wco_password=password
```

If the information is not able to be found in the config file, the program will prompt you directly.

### Config options:
below are the keywords that can be specified in a `config.txt` file

| keyword                       | required for                                                                           | description                                                                                 |
| ----------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `wco_host`                    | process_overdues, dupe_checkouts, overdues, open_fines, serial_search, checkout_emails | base url to the service side of the WebCheckout instance                                    |
| `wco_user_id`                 | process_overdues, dupe_checkouts, overdues, open_fines, serial_search, checkout_emails | username for the webcheckout account to sign in with                                        |
| `wco_password`                | process_overdues, dupe_checkouts, overdues, open_fines, serial_search, checkout_emails | password for the webcheckout account to sign in with                                        |
| `redmine_host`                | process_overdues                                                                       | base url for the redmine instance                                                           |
| `redmine_auth_key`            | process_overdues                                                                       | authentication key for the redmine account to use                                           |
| `project_query_ext`           | process_overdues                                                                       | project url extension after `redmine_host`                                                  |
| `postgres`                    | process_overdues                                                                       | password to the postgresql database (uses username of `postgres`)                           |
| `register_changes_email`      | process_overdues                                                                       | email to contact regarding necessary registrar hold changes                                 |
| `register_changes_name_first` | process_overdues                                                                       | first name of contact for registrar hold changes                                            |
| `register_changes_name_last`  | process_overdues                                                                       | last  name of contact for registrar hold changes                                            |
| `ebling_contact`              | process_overdues                                                                       | contact(s) for Ebling Library InfoLab (seperate multiple emails with spaces)                |
| `merit_contact`               | process_overdues                                                                       | contact(s) for MERIT Library InfoLab (seperate multiple emails with spaces)                 |
| `steenbock_contact`           | process_overdues                                                                       | contact(s) for Steenbock Library InfoLab (seperate multiple emails with spaces)             |
| `business_contact`            | process_overdues                                                                       | contact(s) for Business Library InfoLab (seperate multiple emails with spaces)              |
| `social_work_contact`         | process_overdues                                                                       | contact(s) for Social Work Library InfoLab (seperate multiple emails with spaces)           |
| `college_memorial_contact`    | process_overdues                                                                       | contact(s) for College and Memorial Library InfoLabs (seperate multiple emails with spaces) |

## Support
Developer: Elias Cassis

Area: Internal Tools