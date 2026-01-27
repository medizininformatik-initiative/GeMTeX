import logging
import re
import unicodedata

import numpy as np
from Levenshtein import distance as levenshtein_distance

# Liste der Abkürzungen für medizinische Einrichtungen und Geschäftliche Formen
abbreviations = {
    # Medizinische Fachbereiche und Einrichtungen
    "HNO": "Hals-Nasen-Ohren",
    "MKG": "Mund-, Kiefer- und Gesichtschirurgie",
    "FA": "Facharzt",
    "ZA": "Zahnarzt",
    "KH": "Krankenhaus",
    "LKH": "Landeskrankenhaus",
    "MVZ": "Medizinisches Versorgungszentrum",
    "ZMVZ": "Zahnmedizinisches Versorgungszentrum",
    "PHV": "Patientenheimversorgung",
    "ZAR": "Zentrum für ambulante Rehabilitation",
    "KJPP": "Kinder- und Jugendpsychiatrie und Psychotherapie",
    "UK": "Universitätsklinikum",
    "BG": "Berufsgenossenschaftliches Krankenhaus",
    "REHA": "Rehabilitationsklinik",
    "KG": "Krankengymnastik",
    "KHB": "Krankenhausbetriebsgesellschaft",
    "SPZ": "Sozialpädiatrisches Zentrum",
    "EVK": "Evangelisches Krankenhaus",
    "CVK": "Christliches Krankenhaus",
    "DRK": "Deutsches Rotes Kreuz",
    "VKK": "Verbundkrankenhaus",
    "MLK": "Malteser Krankenhaus",
    "KFO": "Kieferorthopädische Fachklinik",
    "ZPM": "Zentrum für Psychische Gesundheit",
    "ZNA": "Zentrale Notaufnahme",
    "KFH": "Kuratorium für Dialyse und Nierentransplantation",
    "PKV": "Privatklinik für Versicherte",

    # Geschäftliche Rechtsformen
    "e.V.": "Eingetragener Verein",
    "GmbH": "Gesellschaft mit beschränkter Haftung",
    "KGaA": "Kommanditgesellschaft auf Aktien",
    "GmbH & Co. KG": "Kombination aus GmbH und Kommanditgesellschaft",
    "GbR": "Gesellschaft bürgerlichen Rechts",
    "AG": "Aktiengesellschaft",
    "OHG": "Offene Handelsgesellschaft",
    "SE": "Europäische Aktiengesellschaft",
    "PartG": "Partnerschaftsgesellschaft",
    "PartGmbB": "Partnerschaftsgesellschaft mit beschränkter Berufshaftung",
}

# List of substrings to search for
healthcare_keywords = [
    # Allgemeine Begriffe
    "arzt", "ärzt", "chirurg", "gemeinschaft", "klinik", "logie", "ologe",
    "medizin", "praxis", "sanatorium", "therapie", "ambulanz",

    # Fachrichtungen und Behandlungen
    "anästhesie", "augen", "cardio", "dental", "derm", "endokrin", "gastro", "gyn",
    "hämo", "kardio", "neuro", "onko", "optik", "ortho", "osteo", "pathie",
    "pädie", "pneumo", "psych", "uro", "zahn", "zähne", "internist",

    # Verfahren und Diagnostik
    "blut", "ct", "diagnostik", "echo", "labor", "mrt", "radio", "rehabil", "spende",

    # Pflege und Behandlungsarten
    "betreuung", "ernährung", "geriatr", "hospiz", "intensiv", "palliativ", "pflege",
    "physio", "rehaklinik", "therapeut",

    # Alternative Medizin
    "akupunkt", "heilpraktiker", "homöo", "naturheil",

    # Einrichtungen und Zentren
    "fach", "kranken", "notfall", "reha", "zentrum", "haus", "test", "spital", "sankt", "st.",

    # Pädiatrie, Frauen und Spezialversorgung
    "diabetes", "frauen", "kinder", "lungen",

    # Zusätzliche Begriffe
    "apotheke", "behandl", "chirurgi", "gesundheitszentrum",
    "klinisch", "untersuch",

    # titel
    "dr", "phil", "univ", "medic", "dres", "med", "dipl", "psych", "dent", "vet",

    # abbreviations
    "hno", "mkg", "fa", "za", "kh", "lkh", "mvz", "zmvz", "phv", "zar", "kjpp", "uk", "bg", "reha", "kg", "khb", "spz",
    "evk", "cvk", "drk", "vkk", "mlk", "kfo", "zpm", "zna", "kfh", "pkv"
]


def load_hospital_names(text_file):
    """
    Load a list of hospital names from a text file.

    This function reads a text file line by line, stripping any leading or trailing whitespace
    from each line. Only non-empty lines are included in the output list.

    Parameters
    ----------
    text_file : str
        The path to the text file containing hospital names, one name per line.

    Returns
    -------
    list of str
        A list of hospital names extracted from the file.
    """
    with open(text_file, 'r', encoding='utf-8') as f:
        hospital_names = [line.strip() for line in f if line.strip()]
    return hospital_names


# Funktion zum Erstellen des regulären Ausdrucks und zum Ersetzen der Abkürzungen
def replace_abbreviation(text, abbreviations):
    """
    Replace abbreviations in a given text with their full forms based on a provided dictionary.

    This function searches for any abbreviations specified as keys in the ``abbreviations`` dictionary
    within the ``text``. If a match is found, it replaces the abbreviation with its corresponding full
    form from the dictionary. The function uses a regular expression with word boundaries to ensure
    that only exact abbreviations are matched (i.e., whole words).

    Parameters
    ----------
    text : str
        The input string where abbreviations are to be replaced.
    abbreviations : dict
        A dictionary where keys are abbreviations (as strings) and values are their full forms (as strings).

    Returns
    -------
    str
        The modified text with all found abbreviations replaced by their full forms.
    """
    # Precompiled regular expression pattern to match any of the abbreviations
    pattern = re.compile(r'\b(' + '|'.join(re.escape(key) for key in abbreviations.keys()) + r')\b')

    # Replace abbreviations in the text using the dictionary
    return pattern.sub(lambda x: abbreviations[x.group()], text)


# helper function to extract the main name before '/'
def get_name(facility):
    """
    Extract the main facility name before any '/' characters.

    This function processes a facility string and extracts the main
    facility name that appears before any '/' character.

    Parameters
    ----------
    facility : str
        The full facility string containing the name and additional info.

    Returns
    -------
    str
        The main facility name.
    """
    return facility.split('/')[0].strip()


def remove_non_alphanumeric(input_string):
    """
    Clean the input hospital name string by:
    - Removing Byte Order Mark (BOM) characters
    - Replacing newlines and carriage returns with a space
    - Removing unwanted special characters and control characters
    - Keeping only alphanumerics, spaces, periods, commas, slashes, hyphens, and specific German characters
    - Converting all text to lowercase
    - Normalizing Unicode to NFC form
    - Normalizing multiple spaces to a single space

    Parameters
    ----------
    input_string : str
        The hospital name string to clean.

    Returns
    -------
    str
        The cleaned and normalized hospital name string.
    """
    # 1. Normalize Unicode to NFC form to ensure consistency
    cleaned = unicodedata.normalize('NFC', input_string)

    # 2. Remove BOM characters
    # Common BOMs: \ufeff (UTF-8), \uFEFF (UTF-16), \uFFFE (Invalid, but included for robustness)
    cleaned = cleaned.replace('\ufeff', '').replace('\uFEFF', '').replace('\uFFFE', '')

    # 3. Replace newlines and carriage returns with a space
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')

    # 4. Remove other control characters (non-printable characters)
    #    This removes characters in the range U+0000 to U+001F and U+007F
    cleaned = re.sub(r'[\x00-\x1F\x7F]', '', cleaned)

    # 5. Define allowed characters:
    #    - Letters (A-Z, a-z) including German umlauts and sharp S (ß)
    #    - Numbers (0-9)
    #    - Spaces
    #    - Periods (.)
    #    - Commas (,)
    #    - Slashes (/)
    #    - Hyphens (-)
    allowed_chars_pattern = re.compile(r'[A-Za-zäöüßÄÖÜẞ0-9\s.,/\-]')

    # 6. Keep only allowed characters
    cleaned = ''.join(allowed_chars_pattern.findall(cleaned))

    # 7. Convert to lowercase
    cleaned = cleaned.lower()

    # 8. Normalize multiple spaces to a single space and strip leading/trailing spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


def extract_sensitive_data(text, nlp, healthcare_keywords):
    """
    Extract named entities and proper nouns from text, filtering out healthcare-related terms.

    Parameters
    ----------
    text : str
        Input text to process.
    healthcare_keywords : list
        List of healthcare-related keywords to filter out.

    Returns
    -------
    list
        Filtered list of unique sensitive words.
    """
    doc = nlp(text)
    unique_substrings = set()

    # Extract named entities of type PERSON, ORG, LOC and proper nouns
    for ent in doc.ents:
        if ent.label_ in ["PER", "ORG", "LOC"]:
            words = ent.text.split()
            # Only add words that don't contain healthcare keywords
            filtered_words = [
                word for word in words
                if not any(keyword in word.lower() for keyword in healthcare_keywords)
            ]
            unique_substrings.update(filtered_words)

    # Extract proper nouns
    for token in doc:
        if token.pos_ == "PROPN":
            # Only add if it doesn't contain healthcare keywords
            if not any(keyword in token.text.lower() for keyword in healthcare_keywords):
                unique_substrings.add(token.text)

    return list(unique_substrings)


def filter_hospitals(hospitals, similarity_scores, sensitive_words) -> list[str]:
    """
    Filter hospitals based on similarity scores and sensitive words.

    Parameters
    ----------
    hospitals : list
        List of hospital names to filter.
    similarity_scores : list
        List of similarity scores corresponding to each hospital.
    sensitive_words : list
        List of sensitive words to filter out.

    Returns
    -------
    list[str]
        Filtered list of hospitals excluding exact matches and those containing sensitive words.
    """
    # Combine the filtering conditions into a single list comprehension
    filtered_hospitals = [
        hospital for hospital, score in zip(hospitals, similarity_scores)
        if score != 1 and not any(
            sensitive_word.lower() in hospital.lower()
            for sensitive_word in sensitive_words
        )
    ]

    return filtered_hospitals


def normalize_levenshtein_distance(str1, str2):
    """
    Calculate the normalized Levenshtein distance between two strings.

    The normalized Levenshtein distance is the ratio of the raw Levenshtein distance to the
    length of the longer string, providing a similarity measure between 0 and 1. A result
    closer to 0 indicates higher similarity, while a result closer to 1 indicates more dissimilarity.

    Parameters
    ----------
    str1 : str
        The first string to compare.
    str2 : str
        The second string to compare.

    Returns
    -------
    float
        The normalized Levenshtein distance, ranging from 0.0 to 1.0.
        Returns 0.0 for two empty strings (an edge case).
    """
    lev_distance = levenshtein_distance(str1, str2)
    max_len = max(len(str1), len(str2))
    if max_len == 0:  # Handle edge case with empty strings
        return 0.0
    return lev_distance / max_len  # Normalize by dividing by the max string length


def calculate_average_distance(target_sensitive_data: list[str], sampled_sensitive_data: list[str]):
    """
    Calculate the average normalized Levenshtein distance between target terms and sampled terms.

    For each word in the target terms, find the closest matching word in the sampled terms,
    and compute the normalized Levenshtein distance between them. The average of these
    minimum distances is returned, adjusted to produce a similarity measure from 0 to 1,
    where higher values indicate greater similarity.

    Parameters
    ----------
    target_sensitive_data : list[str]
        List of target terms (e.g., words related to healthcare in the target hospital).
    sampled_sensitive_data : list[str]
        List of terms from a hospital name to compare against the target terms.

    Returns
    -------
    float
        The average normalized Levenshtein distance, where 1 indicates perfect similarity
        and values closer to 0 indicate dissimilarity.
    """
    total_distance = 0
    num_comparisons = len(target_sensitive_data)

    # For each target term, find the closest match in the sampled terms
    for target_substring in target_sensitive_data:
        min_distance = float('inf')  # Initialize with a large value

        for sampled_substring in sampled_sensitive_data:
            normalized_distance = normalize_levenshtein_distance(target_substring.lower(), sampled_substring.lower())
            if normalized_distance < min_distance:
                min_distance = normalized_distance

        # Accumulate the smallest distance for this target term
        total_distance += min_distance

    # Calculate the average normalized distance
    if num_comparisons == 0:
        return 0.0
    return 1 - (total_distance / num_comparisons)


def calculate_hospital_probabilities(ranked_hospitals, temperature=0.1):
    """
    Calculate a probability distribution over hospitals based on their distances using a sigmoid function and temperature scaling.

    Parameters
    ----------
    ranked_hospitals : list of tuples
        A list where each element is a tuple of (hospital, distance).
    temperature : float
        A scaling factor to adjust the sharpness of the probability distribution.

    Returns
    -------
    tuple
        A tuple containing:
        - hospitals : tuple
            A tuple of hospital identifiers.
        - probabilities : numpy.ndarray
            An array of probabilities corresponding to each hospital.
    """
    # Split the hospitals and distances
    hospitals, distances = zip(
        *ranked_hospitals)  # TODO ranked_hospitals could be empty, handle the exceptions --> Meulengracht_gemtex.xmi
    distances = np.array(distances)

    # Apply sigmoid function to distances
    sigmoid_distances = 1 / (1 + np.exp(-distances))

    # Apply temperature scaling to make the distribution sharper
    scaled_scores = sigmoid_distances ** (1 / temperature)

    # Normalize the scaled scores to create a probability distribution
    probabilities = scaled_scores / np.sum(scaled_scores)

    return hospitals, probabilities


def rank_hospitals_by_similarity(target_hospital, filtered_hospitals, healthcare_keywords):
    """
    Identify and rank hospitals based on the similarity of healthcare-related terms in the target hospital name.

    Parameters
    ----------
    target_hospital : str
        The name of the target hospital to compare against.
    filtered_hospitals : list of str
        A list of hospital names to be evaluated.
    healthcare_keywords : list of str
        A list of keywords representing healthcare-related terms.

    Returns
    -------
    list of tuples
        A list of tuples where each tuple contains a hospital name and its average normalized
        Levenshtein distance to the healthcare-related terms in the target hospital. Only hospitals
        with an average distance above or equal to 0.5 are included.
    """
    # Extract healthcare-related words from the target hospital name
    healthcare_terms = [word for word in re.split(r'[ \-]', target_hospital) if
                        any(keyword in word.lower() for keyword in healthcare_keywords)]

    ranked_hospitals = []
    # Calculate average normalized Levenshtein distance for each hospital
    for hospital in filtered_hospitals:
        avg_distance = calculate_average_distance(healthcare_terms, re.split(r'[ \-]', hospital))

        ranked_hospitals.append((hospital, avg_distance))
    # Keep only those that collectively account for the top 50% of sum
    ranked_hospitals = get_top_50_percent(ranked_hospitals)

    return ranked_hospitals


def get_top_50_percent(hospital_distance_list: list[tuple[str, int]]):
    """
    Select the smallest subset of hospitals whose cumulative scores account for at least 50%
    of the total distance, prioritizing higher scores first.

    Parameters
    ----------
    hospital_distance_list : list[tuple[str, int]]
        A list of (hospital name, distance) tuples.

    Returns
    -------
    list of tuples
        A subset of the input list containing the top contributors to 50% of the total distance.
    """
    if not hospital_distance_list:
        return []

    # Sort by distance descending
    hospital_distance_list.sort(key=lambda x: x[1], reverse=True)

    # Sum all distances
    total_distance = sum(dist for _, dist in hospital_distance_list)
    cutoff = total_distance * 0.5

    # Accumulate from top until we reach at least 50% of total
    top_50pct = []
    cumulative = 0.0
    for hospital, dist in hospital_distance_list:
        top_50pct.append((hospital, dist))
        cumulative += dist
        if cumulative >= cutoff:
            break

    return top_50pct


def query_similar_hospitals(target_sentence, model, nn_model, hospital_names: list[str], top_k=5):
    """
    Query the most similar hospitals based on a target sentence using a pre-trained model
    and a nearest-neighbor model for similarity search.

    Parameters
    ----------
    target_sentence : str
        The input sentence describing the target hospital or criteria.
    model
        A pre-trained model used to compute embeddings for the target sentence.
        Typically, this is a sentence transformer or similar NLP model.
    nn_model
        A trained nearest-neighbor model (e.g., sklearn's NearestNeighbors)
        used for similarity search in the embedding space.
    hospital_names : list[str]
        A list of hospital names corresponding to the entries
        in the embedding space indexed by `nn_model`.
    top_k : int, optional
        The number of most similar hospitals to return. Default is 5.

    Returns
    -------
    tuple
        A tuple containing:
        - results : list
            A list of the top_k most similar hospital names.
        - similarity : list
            A list of similarity scores (float values between 0 and 1)
            corresponding to the top_k results.
    """
    # Compute embedding for the target sentence
    target_embedding = model.encode([target_sentence], convert_to_numpy=True)

    # Perform similarity search with the specified top_k
    distances, indices = nn_model.kneighbors(target_embedding, n_neighbors=top_k)

    # Retrieve the hospital names and their similarity scores
    results = []
    similarity = []
    for idx, distance in zip(indices[0], distances[0]):
        hospital = hospital_names[idx]  # Directly use the list of hospital names
        similarity_score = 1 - distance  # Convert cosine distance to similarity
        results.append(hospital)
        similarity.append(float(similarity_score))
    return results, similarity


def query_similar_hospitals_adaptive(
        target_hospital,
        model,
        nn_model,
        nlp,
        hospital_names: list[str],
        initial_k=10,
        max_k=100,
        step_size=10,
        min_matches=3
):
    """
    Adaptively query for similar hospitals, expanding the search until enough matches are found.

    Parameters
    ----------
    target_hospital : str
        The hospital to find matches for.
    model
        The embedding model used to compute hospital embeddings.
    nn_model
        The nearest neighbor model used for similarity search.
    hospital_names : list[str]
        List of all hospital names.
    initial_k : int
        Initial number of hospitals to retrieve.
    max_k : int
        Maximum number of hospitals to consider.
    step_size : int
        How much to increase `k` by in each iteration.
    min_matches : int
        Minimum number of matches required.

    Returns
    -------
    tuple
        A tuple containing:
        - filtered_hospitals : list
            List of hospitals that match the criteria.
        - similarity_scores : list
            List of similarity scores corresponding to the filtered hospitals.
        - k_used : int
            The final value of `k` used to satisfy the minimum matches.
    """
    current_k = initial_k

    while current_k <= max_k:
        # replace abbreviation with the semantic full form
        target_hospital_extended = replace_abbreviation(target_hospital, abbreviations)

        # Get similar hospitals with current k
        similar_hospitals, similarity_scores = query_similar_hospitals(target_hospital_extended, model, nn_model,
                                                                       hospital_names, top_k=current_k)

        # Apply the get_name function to each similar hospital to remove the healthcare:specialty infromation
        similar_hospitals = [get_name(hospital) for hospital in similar_hospitals]

        # Extract sensitive words
        sensitive_words = extract_sensitive_data(target_hospital_extended, nlp, healthcare_keywords)

        # Filter hospitals
        filtered_hospitals = filter_hospitals(similar_hospitals, similarity_scores, sensitive_words)
        # If we have enough matches, break
        if len(filtered_hospitals) >= min_matches:
            return filtered_hospitals, current_k

        # Increase k for next iteration
        current_k += step_size

        logging.info(f"Insufficient matches found with k={current_k - step_size}, "
                     f"expanding search to k={current_k}")

    # If we get here, we couldn't find enough matches even with max_k
    logging.warning(f"Could not find {min_matches} matches even with k={max_k}")

    return filtered_hospitals, current_k


def get_hospital_surrogate(target_hospital, model, nn_model, nlp, hospital_names: list[str], initial_k=10, max_k=100,
                           min_matches=3):
    """
    Main function to get a surrogate hospital with adaptive search.

    Parameters
    ----------
    target_hospital : str
        The hospital to find matches for.
    model
        The embedding model used to compute hospital embeddings.
    nn_model
        The nearest neighbor model used for similarity search.
    hospital_names : list[str]
        List of all hospital names.
    initial_k : int
        Initial number of hospitals to retrieve.
    max_k : int
        Maximum number of hospitals to consider.
    min_matches : int
        Minimum number of matches required.

    Returns
    -------
    tuple
        A tuple containing:
        - sampled_hospital : str
            The selected surrogate hospital.
        - probabilities : list
            A list of probabilities associated with the selected hospital.
        - hospitals : list
            A list of hospitals considered in the adaptive search.
        - k_used : int
            The final value of `k` used to meet the minimum matches.
    """
    # clean query
    target_hospital = remove_non_alphanumeric(target_hospital)
    # Get similar hospitals with adaptive k search
    similar_hospitals, k_used = query_similar_hospitals_adaptive(
        target_hospital,
        model,
        nn_model,
        nlp,
        hospital_names,
        initial_k=initial_k,
        max_k=max_k,
        min_matches=min_matches
    )
    # Rank hospitals
    ranked_hospitals = rank_hospitals_by_similarity(target_hospital, similar_hospitals, healthcare_keywords)
    # Calculate probabilities and sample
    hospitals, probabilities = calculate_hospital_probabilities(ranked_hospitals)
    sampled_hospital = str(np.random.choice(hospitals, p=probabilities))
    return sampled_hospital, probabilities, hospitals, k_used
