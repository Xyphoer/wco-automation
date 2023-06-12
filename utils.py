from connection import Connection

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
    def check_dupe_types(self, alloc_types, allocs: list) -> bool:
        
        # iterate over all types in the current allocation
        for alloc_type in alloc_types:
            # check this type against other allocations provided in allocs
            for alloc in allocs:
                # only check for laptops and ipads
                if 'laptop' in alloc_type['name'].lower() or 'ipad' in alloc_type['name'].lower():
                    if alloc_type in alloc['activeTypes']:
                        return True
                    # check parent types
                    if alloc_type['parent'] in [type_parent['parent'] for type_parent in alloc['activeTypes']]:
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
                    current = checkouts.pop()['activeTypes']

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
                    current = checkouts.pop()['activeTypes']

                    # compare current to other (if any) checkouts in checkouts
                    if self.check_dupe_types(current, checkouts):
                        # if the patron has duplicate checkouts add their oid to the list
                        patron_duplicates.append(patron_oid)
        
        # return list of patron oids who have duplicate checkouts
        return patron_duplicates
    
    #####
    # Name: patrons_with_duplicate_checkouts
    # Inputs: sorted_allocs (list), connection (Connection)
    # Output: patrons (list)
    # Description: Get patron information for those who have duplicate checkouts
    #####
    def patrons_with_duplicate_checkouts(self, sorted_allocs: list, connection: Connection) -> list:
        # get oids of patrons with duplicate checkouts
        patron_oids = self.check_checkouts(sorted_allocs)
        patrons = []        # hold patrons informations

        for oid in patron_oids:
            # get patron information from WCO
            patrons.append(connection.get_patron(oid))
        
        return patrons