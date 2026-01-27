import logging
import random
import re
import time
from collections import Counter
from collections import defaultdict

from anytree import Node, PreOrderIter
from overpy import Overpass


def safe_query(api: Overpass, query: str, *, max_retries=5, base_delay=2, verbose=True):
    """
    Run an Overpass query with exponential-backoff retries.

    Parameters
    ----------
    api : overpy.Overpass
        The initialized Overpass API object (endpoint already set).
    query : str
        The Overpass QL query string.
    max_retries : int, optional
        How many *additional* attempts after the first one (default 5).
    base_delay : int | float, optional
        Wait time (seconds) after the first failure; doubles each retry.
    verbose : bool, optional
        Print a message before each retry.

    Returns
    -------
    overpy.Result
        The parsed Overpass result object.

    Raises
    ------
    Exception
        Re-raises the last exception if all retries fail.
    """
    for attempt in range(max_retries + 1):  # +1 = initial try + retries
        try:
            return api.query(query)  # <-- normal path
        except Exception as e:  # catch *everything*
            if attempt == max_retries:  # last attempt, give up
                raise
            delay = base_delay * (2 ** attempt)  # 2, 4, 8, ...
            if verbose:
                print(f"[Retry {attempt + 1}/{max_retries}] {e} – "
                      f"retrying in {delay}s …")
            time.sleep(delay)


def find_closest_city_area_code(input_number, tel_dict):
    """
    Finds the closest city using a simplified, direct search logic.

    1.  It iterates backward from the full input number to find the longest
        possible prefix that matches the start of any key(s) in the dictionary.
    2.  Once this "best prefix level" is found, it gathers all keys that
        start with this prefix.
    3.  From this group of candidates, it finds the one whose next digit is
        numerically closest to the input number's next digit.
    4.  If no common prefix is found at all, it returns a "not found" message.

    Args:
        input_number: The phone number string to look up.
        tel_dict: A dictionary with area codes (str or int) as keys and city
                  names (str) as values.

    Returns:
        A tuple: (city_name, matched_vorwahl).
    """
    if not tel_dict:
        return "Dictionary is empty", None

    # --- Step 0: Normalize keys to strings for consistent processing ---
    try:
        normalized_dict = {str(k): v for k, v in tel_dict.items()}
        # Validate that input is numeric, but don't convert to int yet.
        int(input_number)
    except (ValueError, TypeError):
        return "Invalid input: number and keys must be numeric.", None

    # --- Step 1 & 2: Find the longest shared prefix and gather all candidates ---
    for i in range(len(input_number), 0, -1):
        prefix = input_number[:i]

        # Find all dictionary keys that start with this common prefix.
        candidates = [key for key in normalized_dict if key.startswith(prefix)]

        # If we found any candidates, this is our "best prefix level".
        # We can stop searching for shorter prefixes and work with this group.
        if candidates:
            # --- Step 3: From the candidates, find the best match ---

            # If there's only one candidate, we're done. It's the best match.
            if len(candidates) == 1:
                best_match_key = candidates[0]
                return normalized_dict[best_match_key], best_match_key

            # If there are multiple candidates, we find the closest one.
            try:
                # The digit in our input that we want to match.
                target_digit = int(input_number[i])
            except IndexError:
                # This happens if the input is "04" and keys are "041", "042".
                # The input has no "next digit". In this case, we find the
                # key that is numerically closest to the input itself.
                input_as_int = int(input_number)
                best_match_key = min(candidates, key=lambda k: abs(int(k) - input_as_int))
                return normalized_dict[best_match_key], best_match_key

            # --- Apply the "closest next digit" rule ---
            best_match_key = None
            min_difference = float('inf')

            for key in candidates:
                # Make sure the candidate key is long enough to have a "next digit".
                if len(key) > i:
                    try:
                        candidate_digit = int(key[i])
                        difference = abs(target_digit - candidate_digit)

                        # If this candidate is closer, it becomes the new best match.
                        if difference < min_difference:
                            min_difference = difference
                            best_match_key = key
                    except ValueError:
                        # Skip if the character at this position is not a digit.
                        continue

            # If we found a best match, return it. Otherwise, use the first candidate.
            if best_match_key:
                return normalized_dict[best_match_key], best_match_key
            else:
                # Fallback if no key was long enough for the "next digit" comparison
                return normalized_dict[candidates[0]], candidates[0]

    # If the loop completes without finding any matching prefix, no city was found.
    return None, None


def mark_phone_locations(roots, phone_locations):
    """
    Mark nodes in the tree if their names are in phone_locations.

    Parameters
    ----------
    roots : list
        List of root nodes to process
    phone_locations : list
        List of location names to check against
    """
    for root in roots:
        for node in PreOrderIter(root):
            if node.name in phone_locations:
                node.has_phone = (phone_locations[node.name]
                                  if isinstance(phone_locations, dict) else True)


def fetch_location_info(location_list, admin_level, overpass_api):
    """
    Query Overpass for the given locations and return their best admin_level match.

    Parameters
    ----------
    location_list : list of str
        Location names to query.
    admin_level : int
        Fallback admin_level to use if Overpass returns no match for a location.

    Returns
    -------
    dict
        {location_name: {'admin_level': int, 'id': str}}
    """
    escaped = [re.escape(loc) for loc in location_list]
    pattern = '|'.join(escaped)

    query = f"""
    [out:json];
    (
      relation["name"~"^({pattern})$",i]["boundary"="administrative"];
      relation["name:de"~"^({pattern})$",i]["boundary"="administrative"];
    );
    out center tags;
    """
    result = safe_query(overpass_api, query)

    info = {}
    for r in result.relations:
        # For each relation, get name (favoring name:de), admin_level, and relation ID
        name = (r.tags.get("name:de") or r.tags.get("name", "Unknown")).strip()
        lvl_str = r.tags.get("admin_level", "")
        level = int(lvl_str) if lvl_str.isdigit() else 0
        # Check if this is a "Kreisfreie Stadt"
        is_kreisfrei = r.tags.get("admin_title:de", "").strip() == "Kreisfreie Stadt"
        new_level = 8 if is_kreisfrei else level  # treat it like a city, not a district
        # If this location is not yet in the dictionary or we found a 'better' (lower) admin_level
        if name not in info or level < info[name]['admin_level']:
            info[name] = {'admin_level': new_level, 'id': str(r.id)}

    # Ensure that every location passed in is present, even if Overpass returned no matches
    for loc in location_list:
        if loc not in info:
            info[loc] = {'admin_level': admin_level, 'id': "00000"}
    return info


def group_locations_by_admin_level(locations_data):
    """
    Group locations by their admin_level.

    Parameters
    ----------
    locations_data : dict
        {location_name: {'admin_level': int, 'id': str}}

    Returns
    -------
    dict
        {admin_level: [{'name': str, 'id': str}, ...]}
    """
    grouped = {}
    for location_name, data in locations_data.items():
        level = data['admin_level']
        entry = {'name': location_name, 'id': data['id']}
        if level not in grouped:
            grouped[level] = []
        grouped[level].append(entry)

    # Sort locations within each admin level by name
    for level in grouped:
        grouped[level].sort(key=lambda x: x['name'])

    return grouped


def get_state(osm_id, overpass_api):
    """
    Retrieves the Bundesland (state) information for a given OSM relation ID.

    Parameters:
        osm_id (int): The OSM relation ID of the place.

    Returns:
        tuple: (state_name, state_osm_id) if found, else (None, None).
    """
    # Query to fetch the relation using its OSM ID and get its center point
    query_place = f"""
    [out:json];
    relation({osm_id});
    out center;
    """

    try:
        result_place = safe_query(overpass_api, query_place)

    except Exception as e:
        logging.error(f"Error fetching place with OSM ID {osm_id}: {e}")
        return None, None

    if not result_place.relations:
        logging.warning(f"No relation found for OSM ID {osm_id}.")
        return None, None

    place_relation = result_place.relations[0]

    # Ensure that the relation has a center point
    if not hasattr(place_relation, 'center_lat') or not hasattr(place_relation, 'center_lon'):
        logging.warning(f"Relation {osm_id} does not have a center point.")
        return None, None

    center_lat = place_relation.center_lat
    center_lon = place_relation.center_lon

    # Query to find the Bundesland containing the center point
    query_bundesland = f"""
    [out:json];
    is_in({center_lat},{center_lon});
    relation(pivot)["boundary"="administrative"]["admin_level"="4"];
    out ids tags;
    """

    try:
        result_bundesland = safe_query(overpass_api, query_bundesland)
    except Exception as e:
        logging.error(f"Error fetching Bundesland for OSM ID {osm_id}: {e}")
        return None, None

    if not result_bundesland.relations:
        logging.warning(f"No Bundesland found containing OSM ID {osm_id}.")
        return None, None

    bundesland_relation = result_bundesland.relations[0]
    state_name = bundesland_relation.tags.get("name:de")
    state_osm_id = bundesland_relation.id

    if not state_name:
        logging.warning(f"Bundesland relation {state_osm_id} lacks a name tag.")
        return None, None

    return state_name, state_osm_id


def get_random_osm_state(overpass_api: Overpass):
    """
    Fetches a random German state (Bundesland) from OpenStreetMap.
    This is a fallback if no other state information is available to build the hierarchy.

    Parameters
    ----------
    overpass_api : overpy.Overpass
        Overpass API instance.

    Returns
    -------
    tuple
        (state_name, state_osm_id_str) if found, else (None, None).
        state_osm_id_str is the OSM ID as a string.
    """
    # Query for administrative boundaries at admin_level 4 (states in Germany)
    # that have a "name:de" tag to prefer German names.
    query = """
    area["ISO3166-1"="DE"]->.searchArea;
    relation["boundary"="administrative"]["admin_level"="4"]["name:de"](area.searchArea);
    out center tags;
    """
    try:
        result = safe_query(overpass_api, query)
        if result.relations:
            random_state = random.choice(result.relations)
            state_name = random_state.tags.get("name:de") or random_state.tags.get("name")
            return state_name, str(random_state.id)
    except Exception:
        pass
    return None, None


def build_hierarchy(locations_by_level, street_locations, overpass_api):
    """
    Build a hierarchy of administrative nodes.
    After building the graph, iterate through the leaves and attempt to find a street for each.
    Once a single leaf with a matching street is found, add that street as a child to that leaf and stop.

    Parameters
    ----------
    locations_by_level : dict
        {admin_level: [{'name': str, 'id': int or None}, ...]}

    Returns
    -------
    dict
        Hierarchy nodes with the built hierarchy.
    """

    all_nodes = {}
    missing_nodes = []

    def is_child(parent_id: int, child_name: str, overpass_api: Overpass):
        """
        Check if child_name is within parent_id's area.

        Parameters
        ----------
        parent_id : int
            OSM relation ID of the parent area.
        child_name : str
            Name of the child area.
        overpass_api : overpy.Overpass
            Overpass API instance.

        Returns
        -------
        int or None
            Child's relation ID if found, else None.
        """
        query = f"""
        [out:json];
        relation({parent_id})->.parent;
        .parent map_to_area -> .parentArea;
        relation["name"~"^{re.escape(child_name)}$",i]["boundary"="administrative"](area.parentArea);
        out ids;
        """
        try:
            result = safe_query(overpass_api, query)
            return result.relations[0].id if result.relations else None
        except Exception:
            return None

    def create_or_get_node(name, node_id, level):
        if node_id in all_nodes:
            return all_nodes[node_id]

        node = Node(name, id=node_id)
        node.admin_level = level
        all_nodes[node_id] = node

        if level == 2:
            return node

        higher_levels = sorted([x for x in locations_by_level if x < level], reverse=True)
        parent_found = False

        for hl in higher_levels:
            for p_info in locations_by_level[hl]:
                p_id = p_info['id']
                if p_id and is_child(p_id, name, overpass_api):
                    p_node = create_or_get_node(p_info['name'], p_id, hl)
                    node.parent = p_node
                    parent_found = True
                    break
            if parent_found:
                break

        # If no parent with admin_level=4 is found, fetch and create Bundesland
        if not parent_found and level > 4:
            state_name, state_id = get_state(node_id, overpass_api)
            if state_name and state_id:
                # Create Bundesland node if not already created
                if state_id not in all_nodes:
                    state_node = Node(state_name, id=state_id, admin_level=4)
                    all_nodes[state_id] = state_node
                else:
                    state_node = all_nodes[state_id]

                # Set as parent
                node.parent = state_node

        return node

    def clean_street_name(name):
        """
        Cleans and standardizes street names by handling common variations and formats.

        This function:
        1. Removes leading/trailing whitespace
        2. Separates street name from number/details
        3. Standardizes 'Str.' to 'Straße' while preserving case

        Parameters
        ----------
        name : str
            Input street name, potentially with number/details (e.g., "Main Str. 123")

        Returns
        -------
        tuple
            Contains:
            - name : str
                Unaltered street name
            - standardized_name : str
                Street name with 'Str.' expanded to 'Straße' and without number
            - has_number : bool
                True if street address contains a number
        """
        # Remove leading and trailing whitespace
        name = name.strip()

        # Pattern to separate street name from number/details
        pattern = re.compile(r'(\D+)\s*(\d.*)?')
        match = pattern.match(name)

        if match:
            # Extract street name and optional number parts
            street_name, number = match.groups()
            street_name = street_name.strip()

            # Pattern to find 'Str.' (case insensitive)
            str_pattern = re.compile(r'Str\.', re.IGNORECASE)

            # Check if street name contains 'Str.'
            if str_pattern.search(street_name):
                # Determine case of replacement based on original
                if street_name[-4].isupper():  # Check if 'S' in 'Str.' is uppercase
                    street_name = str_pattern.sub('Straße', street_name)
                else:
                    street_name = str_pattern.sub('straße', street_name)

            return name, street_name, number is not None

    def find_one_street_in_area(parent_id, street_name):
        query = f"""
        [out:json];
        relation({parent_id})->.parent;
        .parent map_to_area -> .parentArea;
        way["highway"]["name"~"^{re.escape(street_name)}$"](area.parentArea);
        out ids;
        """
        try:
            res = safe_query(overpass_api, query)
            if res.ways:
                return street_name, res.ways[0].id
        except Exception:
            pass
        return None

    # Create all nodes
    for level in sorted(locations_by_level.keys(), reverse=True):
        for entry in locations_by_level[level]:
            if entry['id'] != "00000":
                create_or_get_node(entry['name'], entry['id'], level)
            else:
                node = Node(entry['name'], admin_level=level, id=entry['id'])
                missing_nodes.append(node)

    # Check if a state-level node (admin_level=4) exists in all_nodes.
    # If not, try to fetch a random state and add it.
    state_exists_in_tree = False
    for node_obj in all_nodes.values():  # Iterate through the Node objects directly
        if hasattr(node_obj, 'admin_level') and node_obj.admin_level == 4:
            state_exists_in_tree = True
            break

    if not state_exists_in_tree:
        state_name, state_id_str = get_random_osm_state(overpass_api)  # state_id_str is already a string
        if state_name and state_id_str:
            if state_id_str not in all_nodes:  # Add only if not already present
                # Create the state node. It will be a root by default as no parent is assigned here.
                state_node = Node(state_name, id=state_id_str, admin_level=4)
                all_nodes[state_id_str] = state_node  # Add to the main collection of nodes

    # Clean street names and store originals with standardized versions
    remaining_streets = [(original, standardized, has_number)
                         for name in street_locations
                         for original, standardized, has_number in [clean_street_name(name)]]

    # For each street, find exactly one leaf that contains it (the first leaf that matches), and assign it there—no
    # other leaves should get this street.
    leaves = [node for node in all_nodes.values() if node.is_leaf and node.id]
    for leaf in leaves:
        # If we've run out of candidate streets, stop.
        if not remaining_streets:
            break

        # Iterate over the remaining streets
        # we only assign one street per leaf
        for i, (name, standardized_name, has_number) in enumerate(remaining_streets):
            street_info = find_one_street_in_area(leaf.id, standardized_name)
            if street_info:
                _, way_id = street_info
                # Attach the street to this leaf
                Node(name, id=way_id, admin_level=11, has_number=has_number, parent=leaf)
                # Remove from the pool so it won't be used again
                remaining_streets.pop(i)
                # Move on to the next leaf (stop checking more streets for *this* leaf)
                break

    # Any streets left at this point weren't assigned to a leaf,
    missing_nodes.extend(
        Node(name, id="00000", has_number=has_number, admin_level=11) for (name, _, has_number) in remaining_streets)
    # for node in missing_nodes:
    #     all_nodes[random.randint(00000, 99999)] = node
    return all_nodes, missing_nodes


def add_zip(node, postal_code):
    """
    Append `postal_code` to node.zip …

       – absent  → create string
       – string  → convert to list + append
       – list    → append (deduplicating)
    """
    if not hasattr(node, 'zip'):
        node.zip = postal_code
    else:
        if isinstance(node.zip, list):
            if postal_code not in node.zip:
                node.zip.append(postal_code)
        else:  # was single string
            if postal_code != node.zip:
                node.zip = [node.zip, postal_code]


def update_tree_with_zip_codes(postal_codes, roots, overpass_api):
    """
    Assign postal code attributes to nodes whose areas match the postal codes in the provided set.
    If no direct match is found for a postal code, it will be assigned to a city-level node without a postal code.

    Parameters
    ----------
    postal_codes : set
        A set of postal codes to query using the Overpass API. These represent the areas of interest.
    roots : list
        A list of root nodes representing the hierarchical tree structure.

    Returns
    -------
    None
        The function modifies the nodes in place.
    """
    # Create a regex pattern to match postal codes
    postal_code_filter = '|'.join(map(str, postal_codes))

    # Build the Overpass QL query to fetch areas with specified postal codes
    query = f"""
    area["boundary"="postal_code"]["postal_code"~"^({postal_code_filter})$"];
    out center;
    """

    try:
        # Execute the Overpass API query
        result = safe_query(overpass_api, query)
    except Exception:
        result = type("dummy", (), {"areas": []})()  # fallback dummy if error

    # Dictionary to store postal code names
    postal_code_names = {}

    # Use a regular expression to separate the numerical and textual parts
    pattern = re.compile(r'(\d+)\s*(.*)')  # d=digit s=white space .=any character

    # Process each area returned by the Overpass API
    for area in result.areas:
        # Extract the 'note' tag which contains postal code information
        note = area.tags.get('note', '')

        # Use regex to separate the numerical and textual parts of the note
        match = pattern.match(note)
        if match:
            postal_code, name = match.groups()
            postal_code_names[postal_code] = name

    # Collect all nodes from the root trees using pre-order traversal
    all_nodes = []
    for root in roots:
        all_nodes.extend(PreOrderIter(root))

    # Assign zip codes to nodes based on matching names
    for postal_code, name in postal_code_names.items():
        for node in all_nodes:
            if node.name in name:
                add_zip(node, postal_code)

                # collect every zip that actually ended up on a node
    attached = set()
    for node in all_nodes:
        if hasattr(node, 'zip'):
            if isinstance(node.zip, list):
                attached.update(str(z) for z in node.zip)
            else:
                attached.add(str(node.zip))

    # compute the list of "still missing" postal codes:
    #    any code not attached
    #    any code never seen in postal_code_names
    missing_postal_codes = [pc for pc in postal_codes if str(pc) not in attached]

    # Iterate through all nodes to assign the remaining postal codes
    preferred_levels = [8, 9, 10, 7, 6, 5, 4]  # 8 first (city-level nodes), then fall-back levels

    for level in preferred_levels:
        if not missing_postal_codes:  # we are done
            break

        for node in all_nodes:
            if node.admin_level != level:  # skip nodes of other levels
                continue
            if getattr(node, "zip", None):  # already has a ZIP
                continue
            if not missing_postal_codes:  # ran out while looping
                break

            # assign the next un-used postal code
            add_zip(node, missing_postal_codes.pop(0))


def gather_nodes_by_admin_level(roots):
    """
    Index nodes by their administrative levels from a hierarchy of root nodes.
    This function traverses a forest of root nodes and collects all nodes in a dictionary,

    Parameters
    ----------
    roots : list of Node
        A list of root nodes representing different hierarchical trees. Each node is expected to have:
            - 'admin_level' (int): The administrative level of the node.
            - 'id' (str): The unique identifier of the node.
            - 'children' (list): A list of child nodes.

    Returns
    -------
    dict
        A dictionary where keys are `admin_level` values (int) and values are lists of Node objects
        at that level.
    """
    level_dict = defaultdict(list)

    def visit(node):
        level_dict[node.admin_level].append(node)
        for child in node.children:
            visit(child)

    for r in roots:
        visit(r)

    return level_dict


def insert_loose_nodes(roots, found_by_level, loose_nodes):
    """
    Insert loose nodes into the hierarchy by matching their administrative level.

    This function places loose nodes under an appropriate parent node based on their `admin_level`.
    If a suitable parent is found, the node is attached to a randomly chosen parent at the
    appropriate level. If no valid parent exists, the node is added as a new root.

    Parameters
    ----------
    roots : list of Node
        A list of root nodes representing the hierarchical tree structure. New root nodes
        will be appended here if no parent is found for a loose node.
    found_by_level : dict
        A dictionary mapping `admin_level` (int) to lists of Node objects at that level.
        This is used to efficiently locate potential parent nodes for loose nodes.
    loose_nodes : list of Node
        A list of nodes that need to be inserted into the hierarchy. Each node is expected to have:
            - 'admin_level' (int): The administrative level of the node.
            - 'id' (str): The unique identifier of the node.

    Returns
    -------
    None
        This function modifies `roots` in place by adding and attaching
        loose nodes to the appropriate locations.
    """

    for mnode in loose_nodes:
        parent_assigned = False  # Track if we found a parent
        decrease_admin_level = 1

        while True:
            parent_level = mnode.admin_level - decrease_admin_level

            if parent_level < 2:
                roots.append(mnode)
                parent_assigned = True  # Mark as root, stop looking for parent

                # register this new root as a possible parent for others
                found_by_level.setdefault(mnode.admin_level, []).append(mnode)
                break

            if parent_level not in found_by_level:
                decrease_admin_level += 1
            else:
                break  # Found a valid parent level

        if parent_assigned:
            continue  # Skip the rest if already assigned as a root

        possible_parents = found_by_level[parent_level]
        # assign the loose node to a random parent at the appropriate level
        mnode.parent = random.choice(possible_parents)

        # register this attached node as a parent candidate for others
        found_by_level.setdefault(mnode.admin_level, []).append(mnode)


def get_postal_code(relation_id, overpass_api):
    """
    Determine a postal code for a given administrative relation using OpenStreetMap data via Overpass API.

    Strategy (now three steps):

        Step 1: Look for `boundary=postal_code` relations completely inside the admin area.
        Step 2: If none, collect all `addr:postcode` values inside the area and
                return the most common one (mode).
        Step 3: If still none, use the centre point of the admin relation with Overpass
                `is_in()` to find an enclosing postal-code boundary.

    Returns
    -------
    str | None
        The postal code string if found, otherwise None.
    """

    # ------------------------------------------------------------
    # Step 1 – postal-code boundaries inside the admin area
    # ------------------------------------------------------------
    query_inside = f"""
    [out:json][timeout:25];
    relation({relation_id})->.place;
    .place map_to_area -> .placeArea;
    relation["boundary"="postal_code"](area.placeArea);
    out center tags;
    """
    try:
        result = safe_query(overpass_api, query_inside)
        if result.relations:
            sample = random.choice(result.relations)
            return sample.tags.get("postal_code")
    except Exception as e:
        logging.error(f"Error (inside) retrieving postal code for {relation_id}: {e}")

    # ------------------------------------------------------------
    # Step 2 – look at address data inside the admin area
    # ------------------------------------------------------------
    query_addresses = f"""
    [out:json][timeout:60];
    relation({relation_id})->.place;
    .place map_to_area -> .placeArea;
    (
      node(area.placeArea)["addr:postcode"];
      way(area.placeArea)["addr:postcode"];
      relation(area.placeArea)["addr:postcode"];
    );
    out tags;
    """
    try:
        result = safe_query(overpass_api, query_addresses)
        # Collect all addr:postcode tags from nodes, ways and relations
        all_elems = result.nodes + result.ways + result.relations
        postcodes = [el.tags.get("addr:postcode") for el in all_elems if el.tags.get("addr:postcode")]
        if postcodes:
            # Return the most frequently occurring postcode
            most_common, _ = Counter(postcodes).most_common(1)[0]
            return most_common
    except Exception as e:
        logging.error(f"Error (addresses) retrieving postal code for {relation_id}: {e}")

    # ------------------------------------------------------------
    # Step 3 – fallback: centre point + is_in()
    # ------------------------------------------------------------
    try:
        rel_query = f"""
        [out:json];
        relation({relation_id});
        out center;
        """
        rel = safe_query(overpass_api, rel_query).relations[0]
        lat, lon = rel.center_lat, rel.center_lon

        query_isin = f"""
        [out:json];
        is_in({lat},{lon});
        relation(pivot)["boundary"="postal_code"];
        out center tags;
        """
        result = safe_query(overpass_api, query_isin)
        if result.relations:
            sample = random.choice(result.relations)
            return sample.tags.get("postal_code")
    except Exception as e:
        logging.error(f"Error (is_in) retrieving postal code for {relation_id}: {e}")

    return None


def sample_child_relation(parent_id, child_admin_level, overpass_api):
    """
    Find a random child relation within a specified parent relation area.
    Supports both administrative boundaries and streets (admin_level=99).
    In scenarios where no relation is found for the specified administrative
    level within the area, the function dynamically increments the admin level
    and continues the search until a valid result is retrieved.

    Parameters
    ----------
    parent_id : int
        The OSM relation ID of the parent area.
    child_admin_level : int
        The administrative level to search for (99 for streets).
    api : overpy.Overpass
        An instance of the Overpass API.

    Returns
    -------
    tuple
        (child_name, child_id) if found, else (None, None).
    """
    # Define query templates
    queries = {
        'street': """
            [out:json];
            relation({parent_id})->.parent;
            .parent map_to_area -> .parentArea;
            way["highway"]["name"](area.parentArea);
            out center;
        """,
        'admin': """
            [out:json];
            relation({parent_id})->.parent;
            .parent map_to_area -> .parentArea;
            relation["boundary"="administrative"]
                   ["admin_level"="{child_level}"]
                   (area.parentArea);
            out center;
        """
    }

    while True:
        # Select appropriate query based on admin_level
        is_street = child_admin_level == 99
        query = queries['street'] if is_street else queries['admin']

        # Format query with parameters
        formatted_query = query.format(parent_id=parent_id, child_level=child_admin_level)
        try:
            # Execute query
            result = safe_query(overpass_api, formatted_query)

            # Process results based on type
            if is_street and result.ways:
                sample = random.choice(result.ways)
                return sample.tags.get('name'), sample.id
            elif not is_street and result.relations:
                sample = random.choice(result.relations)
                return sample.tags.get('name'), sample.id

            # If no results, increment admin level and try again
            child_admin_level += 1

        except Exception as e:
            logging.error(f"Error in sample_child_relation: {e}")
            return None, None


def regex_phone_number(phone_number):
    """
    Extract area code from a phone number.
    Expects format like: +49 30 297 43333 or similar
    Returns only the area code part (e.g., '30')

    Parameters
    ----------
    phone_number : str
      Phone number starting with + followed by country code

    Returns
    -------
    str or None
      Area code if found, None if no match
    """
    if not phone_number:
        return None

    # Pattern matches: + followed by digits, space, then captures digits until next space
    pattern = r'^\+\d+\s+(\d+)\s'
    match = re.match(pattern, phone_number)
    return match.group(1) if match else None


def get_area_code(relation_id, api):
    """
    Get a random phone number from objects within an OSM administrative boundary.

    Parameters
    ----------
    relation_id : int
      OSM relation ID for the area to search in
    api : overpy.Overpass
      Initialized Overpass API instance

    Returns
    -------
    str or None
      A random phone number if found, None otherwise
    """
    area_id = 3600000000 + int(relation_id)  # Convert relation ID to area ID

    query = f"""
  [out:json];
  area({area_id})->.a;
  (
    nwr(area.a)["phone"];
    nwr(area.a)["contact:phone"];
  )->.p;
  .p out tags center 1;
  """

    try:
        result = api.query(query)
        # Get the single returned element
        elements = result.nodes + result.ways + result.relations

        if not elements:
            return None

        element = elements[0]
        # Return its phone number (try both phone tags)
        return regex_phone_number(element.tags.get("phone") or element.tags.get("contact:phone"))

    except Exception as e:
        logging.error(f"Error querying phone numbers: {e}")
        return None


def rebuild_tree(root_node, overpass_api):
    """
    Rebuild a tree structure starting from the given root_node.

    Parameters
    ----------
    root_node : Node
        The root node of the tree to rebuild.

    Returns
    -------
    list
        A list of new root nodes for the rebuilt tree.
    """
    new_nodes = []

    def rebuild_subtree(original_node, new_parent=None):
        """
        Recursively rebuild the subtree for the given original_node.
        Attach the new node to new_parent if provided.
        """
        if new_parent is None:
            # For root node, keep original properties
            new_node = Node(
                original_node.name,
                parent=new_parent,
                admin_level=original_node.admin_level,
                id=original_node.id
            )
            # If the original node had a zip attribute, fetch a postal code for the new_node
            if hasattr(original_node, 'zip'):
                postal_code = get_postal_code(new_node.id, overpass_api)
                if postal_code:
                    new_node.zip = postal_code
            # If the original node had a phone attribute, fetch a area code for the new_node
            if hasattr(original_node, 'has_phone'):
                area_code = get_area_code(new_node.id, overpass_api)
                if area_code:
                    new_node.has_phone = area_code
            new_nodes.append(new_node)
        else:
            # For non-root nodes, sample new ones
            sampled_name, sampled_id = sample_child_relation(new_parent.id, original_node.admin_level, overpass_api)
            if sampled_name and sampled_id:
                new_node = Node(
                    sampled_name,
                    parent=new_parent,
                    admin_level=original_node.admin_level,
                    id=sampled_id
                )
                # If the original node had a zip attribute, fetch a postal code for the new_node
                if hasattr(original_node, 'zip'):
                    orig_zips = original_node.zip if isinstance(original_node.zip, list) else [original_node.zip]
                    for _ in orig_zips:  # one fresh sample per original ZIP
                        pc = get_postal_code(new_node.id, overpass_api)
                        if pc:
                            add_zip(new_node, pc)
                        else:
                            print(f"No postal code found for {new_node.name}")
                # If the original node had a house number, fetch a house number for the new_node
                if hasattr(original_node, 'has_number'):
                    if original_node.has_number is True:
                        house_number = random.randint(1, 99)
                        new_node.name = f"{new_node.name} {house_number}"
                # If the original node had a phone attribute, fetch a area code for the new_node
                if hasattr(original_node, 'has_phone'):
                    area_code = get_area_code(new_node.id, overpass_api)
                    if area_code:
                        new_node.has_phone = area_code
            else:
                return  # Skip if no sample found

        # Recurse for all children of the current node
        for child in original_node.children:
            rebuild_subtree(child, new_parent=new_node)

    # Start rebuilding the tree from the given root_node
    rebuild_subtree(root_node)
    return new_nodes


def map_trees(old_roots, new_roots):
    """
    Maps nodes between two tree structures using pre-order traversal. Assumes the
    tree structures are identical in terms of shape and traversal order. Parameters
    ----------
    old_roots : list
        List of root nodes from the original trees
    new_roots : list
        List of root nodes from the new trees
    Returns
    -------
    dict
        Dictionary mapping node names from old trees to corresponding node names in new trees
    """
    if len(old_roots) != len(new_roots):
        raise ValueError("The two lists must have the same number of root nodes.")

    mapping = {}

    for old_root, new_root in zip(old_roots, new_roots):
        iter1 = PreOrderIter(old_root)
        iter2 = PreOrderIter(new_root)

        for node1, node2 in zip(iter1, iter2):
            mapping[node1.name] = node2.name

            if hasattr(node1, 'zip') and hasattr(node2, 'zip'):
                zips1 = node1.zip if isinstance(node1.zip, list) else [node1.zip]
                zips2 = node2.zip if isinstance(node2.zip, list) else [node2.zip]

                # extend zips2 so both lists are equal length
                zips2 += zips2 * (len(zips1) - len(zips2))

                for z1, z2 in zip(zips1, zips2):
                    mapping[z1] = z2

            # Map phone attributes
            if hasattr(node1, 'has_phone') and hasattr(node2, 'has_phone'):
                mapping[node1.has_phone] = node2.has_phone

    return mapping


def get_address_location_surrogate(overpass_api, location_state, location_city, street_locations, postal_codes,
                                   phone_area_code, tel_dict):
    # map the given phone area codes to a city name
    phone_locations = {city: area_code
                       for num in phone_area_code
                       for city, area_code in [find_closest_city_area_code(num, tel_dict)]
                       if city}

    # Define the location lists along with their corresponding default admin levels
    location_groups = [
        # (location_country, 2),
        (location_state, 6),
        (phone_locations, 8),
        (location_city, 8), ]

    locations_data = {}
    # Process each group and merge the results
    for loc_list, admin_level in location_groups:
        data = fetch_location_info(loc_list, admin_level=admin_level, overpass_api=overpass_api)
        locations_data.update(data)

    locations_by_level = group_locations_by_admin_level(locations_data)
    all_nodes, loose_nodes = build_hierarchy(locations_by_level, street_locations, overpass_api)
    old_roots = [n for n in all_nodes.values() if n.is_root]
    # Insert loose nodes into the hierarchy
    found_by_level = gather_nodes_by_admin_level(old_roots)
    insert_loose_nodes(old_roots, found_by_level, loose_nodes)
    update_tree_with_zip_codes(postal_codes, old_roots, overpass_api)
    # Mark nodes that correspond to phone locations
    mark_phone_locations(old_roots, phone_locations)

    # Rebuild and print the tree for each root node
    new_roots = [tree_root for root in old_roots for tree_root in rebuild_tree(root, overpass_api)]
    # map between the two trees
    mapping = map_trees(old_roots, new_roots)

    return mapping
