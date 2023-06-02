from connection import Connection

class Utils:

    class dupeCheckouts:

        def check_dupe_types(self, alloc_types, allocs) -> bool:
            for alloc_type in alloc_types:
                for alloc in allocs:
                    if alloc_type in alloc['activeTypes']:
                        return True
                    if alloc_type['parent'] in [type_parent['parent'] for type_parent in alloc['activeTypes']]:
                        return True
                    
            return False
        
        def check_checkouts(self, sorted_allocs) -> list:
            patron_duplicates = []
            checkouts = []
            patron_oid = 0

            for alloc in sorted_allocs:
                
                # if oid is different, onto a new patron, process old
                if patron_oid != alloc['patron']['oid']:
                    # check for checkouts of same item type for previous patron
                    while len(checkouts):
                        current = checkouts.pop()['activeTypes']
                        if self.check_dupe_types(current, checkouts):
                            patron_duplicates.append(patron_oid)

                patron_oid = alloc['patron']['oid']
                checkouts.append(alloc)

                # last checkout, process all for this patron
                if alloc == sorted_allocs[-1]:
                    # check for checkouts of same item type for previous patron
                    while len(checkouts):
                        current = checkouts.pop()['activeTypes']
                        if self.check_dupe_types(current, checkouts):
                            patron_duplicates.append(patron_oid)
            
            return patron_duplicates
        
        def patrons_with_duplicate_checkouts(self, sorted_allocs, connection: Connection):
            patron_oids = self.check_checkouts(sorted_allocs)
            patrons = []

            for oid in patron_oids:
                patrons.append(connection.getPatron(oid))
            
            return patrons