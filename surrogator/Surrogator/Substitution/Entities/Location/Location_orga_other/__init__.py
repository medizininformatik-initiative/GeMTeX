import logging
import re
import unicodedata

import numpy as np
from Levenshtein import distance as levenshtein_distance

# This script is a refactored version of an original script.
# All references to 'abbreviations' and 'healthcare_keywords' have been removed.
# The script has been generalized from 'hospitals' to 'locations'.
# The core logic and structure of the original script have been preserved.

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Load location Names from a Text File
def load_location_names(text_file):
    """
    Load a list of names from a text file.

    This function reads a text file line by line, stripping any leading or trailing whitespace
    from each line. Only non-empty lines are included in the output list.

    Parameters
    ----------
    text_file : str
        The path to the text file containing hospital names, one name per line.

    Returns
    -------
    list of str
        A list of names extracted from the file.
    """
    with open(text_file, 'r', encoding='utf-8') as f:
        names = [line.strip() for line in f if line.strip()]
    return names


# helper function to extract the main name before '/'
def get_main_name(location_string):
    """
    Extract the main location name before any '/' characters.

    This function processes a location string and extracts the main
    name that appears before any '/' character.

    Parameters
    ----------
    location_string : str
        The full location string containing the name and additional info.

    Returns
    -------
    str
        The main location name.
    """
    return location_string.split('/')[0].strip()


def remove_non_alphanumeric(input_string):
    """
    Clean the input location name string by:
    - Removing Byte Order Mark (BOM) characters
    - Replacing newlines and carriage returns with a space
    - Removing unwanted special characters and control characters
    - Keeping only alphanumerics, spaces, periods, commas, slashes, hyphens, and specific German characters
      (if relevant for general locations)
    - Converting all text to lowercase
    - Normalizing Unicode to NFC form
    - Normalizing multiple spaces to a single space

    Parameters
    ----------
    input_string : str
        The location name string to clean.

    Returns
    -------
    str
        The cleaned and normalized location name string.
    """
    # 1. Normalize Unicode to NFC form to ensure consistency
    cleaned = unicodedata.normalize('NFC', input_string)

    # 2. Remove BOM characters
    cleaned = cleaned.replace('\ufeff', '').replace('\uFEFF', '').replace('\uFFFE', '')

    # 3. Replace newlines and carriage returns with a space
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')

    # 4. Remove other control characters (non-printable characters)
    cleaned = re.sub(r'[\x00-\x1F\x7F]', '', cleaned)

    # 5. Define allowed characters:
    #    - Letters (A-Z, a-z) including German umlauts and sharp S (ß)
    #    - Numbers (0-9)
    #    - Spaces
    #    - Periods (.)
    #    - Commas (,)
    #    - Slashes (/)
    #    - Hyphens (-)
    #    Adjust this regex if a different set of characters is expected for general locations.
    allowed_chars_pattern = re.compile(r'[A-Za-zäöüßÄÖÜẞ0-9\s.,/\-]')

    # 6. Keep only allowed characters
    cleaned = ''.join(allowed_chars_pattern.findall(cleaned))

    # 7. Convert to lowercase
    cleaned = cleaned.lower()

    # 8. Normalize multiple spaces to a single space and strip leading/trailing spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


def extract_named_entities_and_proper_nouns(text, nlp):
    """
    Extract named entities (PERSON, ORG, LOC) and proper nouns from text.

    Parameters
    ----------
    text : str
        Input text to process.
    nlp : spacy.lang.xx.Language
        A spaCy language model instance.

    Returns
    -------
    list
        List of unique extracted words from named entities and proper nouns.
    """
    doc = nlp(text)
    unique_substrings = set()

    # Extract named entities of type PERSON, ORG, LOC
    for ent in doc.ents:
        if ent.label_ in ["PER", "LOC"]:
            # Add words from the entity text
            # Using split() to get individual words, similar to original logic
            unique_substrings.update(ent.text.split())

    # Extract proper nouns
    for token in doc:
        if token.pos_ == "PROPN":
            unique_substrings.add(token.text)
    return list(unique_substrings)


def filter_locations(locations, similarity_scores, extracted_terms_from_target):
    """
    Filter locations based on similarity scores and terms extracted from the target location.

    This function filters out locations that are exact semantic matches (similarity score = 1)
    or locations whose names contain any of the specific terms extracted from the target location's name.
    The latter is to avoid suggestions that are too literally similar if a degree of generalization is desired.

    Parameters
    ----------
    locations : list
        List of location names to filter.
    similarity_scores : list
        List of similarity scores corresponding to each location.
    extracted_terms_from_target : list
        List of specific terms (e.g., proper nouns, entity words) extracted from the target location's name.

    Returns
    -------
    list
        Filtered list of locations.
    """
    filtered_locations_list = []
    for loc, score in zip(locations, similarity_scores):
        # Condition 1: Score is not 1 (not an exact semantic match)
        if score == 1:
            continue

        # Condition 2: Location name does not contain any of the extracted target terms
        contains_target_term = False
        for term in extracted_terms_from_target:
            if term.lower() in loc.lower():
                contains_target_term = True
                break

        if not contains_target_term:
            filtered_locations_list.append(loc)

    return filtered_locations_list


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


def calculate_average_similarity_score(target_terms, candidate_terms):
    """
    Calculate the average similarity score based on normalized Levenshtein distance
    between target terms and candidate terms.

    For each word in the target terms, find the closest matching word in the candidate terms,
    and compute the normalized Levenshtein distance between them. The average of these
    minimum distances is then converted to a similarity score (1 - average distance).
    A higher score (closer to 1) indicates greater similarity.

    Parameters
    ----------
    target_terms : list of str
        List of terms from the target location.
    candidate_terms : list of str
        List of terms from a candidate location to compare against the target terms.

    Returns
    -------
    float
        The average similarity score, where 1 indicates perfect similarity
        and values closer to 0 indicate dissimilarity.
    """
    if not target_terms:  # If target has no terms to compare, similarity is undefined or 0
        return 0.0
    if not candidate_terms:  # If candidate has no terms, similarity is 0
        return 0.0

    total_min_distance = 0

    # For each target term, find the closest match in the candidate terms
    for target_term in target_terms:
        min_distance_for_current_target_term = float('inf')

        for candidate_term in candidate_terms:
            normalized_dist = normalize_levenshtein_distance(target_term.lower(), candidate_term.lower())
            if normalized_dist < min_distance_for_current_target_term:
                min_distance_for_current_target_term = normalized_dist

        # If candidate_terms was empty, min_distance_for_current_target_term remains inf.
        # This case is handled by the initial check for empty candidate_terms.
        # If a target_term finds no match (e.g. candidate_terms is not empty but no commonality),
        # its contribution to dissimilarity will be high (min_distance close to 1).
        total_min_distance += min_distance_for_current_target_term

    # Calculate the average normalized distance
    average_normalized_distance = total_min_distance / len(target_terms)

    # Convert average distance to a similarity score
    return 1 - average_normalized_distance


def calculate_location_probabilities(ranked_locations_with_scores, temperature=0.1):
    """
    Calculate a probability distribution over locations based on their similarity scores
    using a sigmoid-like transformation and temperature scaling.

    Parameters
    ----------
    ranked_locations_with_scores : list of tuples
        A list where each element is a tuple of (location_name, similarity_score).
        Higher similarity_score indicates better match.
    temperature : float
        A scaling factor to adjust the sharpness of the probability distribution.
        Lower temperature -> sharper distribution.

    Returns
    -------
    tuple
        A tuple containing:
        - locations : tuple
            A tuple of location identifiers.
        - probabilities : numpy.ndarray
            An array of probabilities corresponding to each location.
    """
    if not ranked_locations_with_scores:
        return (), np.array([])

    locations, scores = zip(*ranked_locations_with_scores)
    scores = np.array(scores, dtype=float)  # Ensure scores are float

    # Apply sigmoid-like function to scores (scores are expected to be similarity, e.g., [0,1])
    # Original code used 1 / (1 + np.exp(-distances)). If 'scores' are similarities, this is consistent.
    transformed_scores = 1 / (1 + np.exp(-scores))

    # Apply temperature scaling to make the distribution sharper or softer
    # Ensure no division by zero or issues with scores being zero if temperature is high
    # Adding a small epsilon if transformed_scores can be zero and (1/temperature) is not integer.
    epsilon = 1e-9
    scaled_scores = (transformed_scores + epsilon) ** (1 / temperature)

    # Normalize the scaled scores to create a probability distribution
    sum_scaled_scores = np.sum(scaled_scores)
    if sum_scaled_scores == 0:  # Avoid division by zero if all scaled_scores are 0
        # Assign uniform probability if sum is zero (e.g., all scores were initially very low or zero)
        num_locations = len(locations)
        probabilities = np.full(num_locations, 1 / num_locations) if num_locations > 0 else np.array([])
    else:
        probabilities = scaled_scores / sum_scaled_scores

    return locations, probabilities


def rank_locations_by_keyword_similarity(target_location_name, filtered_location_names):
    """
    Rank filtered locations based on the similarity of their constituent keywords/terms
    to those in the target location name.

    Parameters
    ----------
    target_location_name : str
        The name of the target location to compare against.
    filtered_location_names : list of str
        A list of location names to be evaluated and ranked.

    Returns
    -------
    list of tuples
        A list of tuples, where each tuple contains a location name and its
        average similarity score to the target location's terms.
        This list is then filtered to include only the top contributors
        that cumulatively account for at least 50% of the total sum of scores.
    """
    # Extract terms from the target location name (e.g., by splitting by space or hyphen)
    # Using lower() for consistency in comparison
    target_location_terms = [word for word in re.split(r'[ \-]+', target_location_name.lower()) if word]
    logging.debug(f"Target location terms for ranking: {target_location_terms}")

    ranked_locations = []
    # Calculate average similarity score for each filtered location
    for loc_name in filtered_location_names:
        candidate_terms = [word for word in re.split(r'[ \-]+', loc_name.lower()) if word]
        avg_sim_score = calculate_average_similarity_score(target_location_terms, candidate_terms)
        logging.debug(f"Location: {loc_name}, Terms: {candidate_terms}, Avg. Similarity Score: {avg_sim_score:.4f}")
        ranked_locations.append((loc_name, avg_sim_score))

    # Filter to keep only those locations whose scores are significant
    # (e.g., collectively account for the top 50% of the sum of scores)
    ranked_locations = get_top_50_percent_by_score(ranked_locations)

    return ranked_locations


def get_top_50_percent_by_score(location_score_list):
    """
    Select the smallest subset of locations whose cumulative scores account for at least 50%
    of the total score, prioritizing higher scores first.

    Parameters
    ----------
    location_score_list : list of tuples
        A list of (location_name, score) tuples.

    Returns
    -------
    list of tuples
        A subset of the input list containing the top contributors to 50% of the total score.
    """
    if not location_score_list:
        return []

    # Sort by score in descending order (higher score is better)
    location_score_list.sort(key=lambda x: x[1], reverse=True)

    # Sum all scores
    total_score = sum(score for _, score in location_score_list if score > 0)  # Consider only positive scores
    if total_score == 0:  # If all scores are zero or negative, return empty or handle as needed
        return []

    cutoff_score = total_score * 0.5

    top_contributors = []
    cumulative_score = 0.0
    for loc_name, score in location_score_list:
        if score <= 0:  # Stop if scores are no longer positive
            break
        top_contributors.append((loc_name, score))
        cumulative_score += score
        if cumulative_score >= cutoff_score:
            break

    return top_contributors


def query_similar_locations(target_sentence, embedding_model, nn_search_model, all_location_names, top_k=5):
    """
    Query the most similar locations based on a target sentence using a pre-trained embedding model
    and a nearest-neighbor model for similarity search.

    Parameters
    ----------
    target_sentence : str
        The input sentence describing the target location or criteria.
    embedding_model
        A pre-trained model (e.g., sentence transformer) to compute embeddings.
    nn_search_model
        A trained nearest-neighbor model (e.g., sklearn's NearestNeighbors or FAISS)
        for similarity search in the embedding space.
    all_location_names : list
        A list of all location names corresponding to the entries
        in the embedding space indexed by `nn_search_model`.
    top_k : int, optional
        The number of most similar locations to return. Default is 5.

    Returns
    -------
    tuple
        A tuple containing:
        - results : list
            A list of the top_k most similar location names.
        - similarity_scores : list
            A list of similarity scores (float values, typically 0 to 1, higher is better)
            corresponding to the top_k results.
    """
    # Compute embedding for the target sentence
    target_embedding = embedding_model.encode([target_sentence], convert_to_numpy=True)

    # Perform similarity search with the specified top_k
    # nn_search_model.kneighbors returns (distances, indices)
    distances, indices = nn_search_model.kneighbors(target_embedding, n_neighbors=min(top_k, len(all_location_names)))

    results = []
    similarity_scores = []
    for i in range(indices.shape[1]):  # Iterate through the found neighbors
        idx = indices[0, i]
        distance = distances[0, i]

        location_name = all_location_names[idx]
        # Convert distance to similarity. Common for cosine distance: similarity = 1 - distance.
        # If using dot product or other metrics, this conversion might change.
        # Assuming distance is something like cosine distance [0, 2] or L2 distance.
        # For cosine similarity from sentence-transformers, distance is often 1-cos_sim.
        # So, similarity_score = 1 - distance is appropriate if distance is cosine distance.
        # If nn_search_model.kneighbors already returns similarity, then this is not needed.
        # Let's assume distance means "dissimilarity".
        similarity_score = 1 - distance

        results.append(location_name)
        similarity_scores.append(float(similarity_score))

    return results, similarity_scores


def query_similar_locations_adaptive(target_location_name, embedding_model, nn_search_model, nlp_processor,
                                     all_location_names, initial_k=10, max_k=100, step_size=10, min_matches=10):
    """
    Adaptively query for similar locations, expanding the search until enough suitable matches are found.

    Parameters
    ----------
    target_location_name : str
        The location name to find matches for.
    embedding_model
        The embedding model.
    nn_search_model
        The nearest neighbor model for similarity search.
    nlp_processor
        A spaCy language model instance for NLP tasks.
    all_location_names : list
        List of all location names in the database/dataset.
    initial_k : int
        Initial number of locations to retrieve semantically.
    max_k : int
        Maximum number of locations to consider retrieving.
    step_size : int
        Increment for `k` in each iteration if not enough matches are found.
    min_matches : int
        Minimum number of filtered matches required to stop expansion.

    Returns
    -------
    tuple
        A tuple containing:
        - final_filtered_locations : list
            List of location names that meet the filtering criteria.
        - k_used : int
            The final value of `k` (number of semantic neighbors retrieved) used.
    """
    current_k = initial_k
    final_filtered_locations = []

    # Extract specific terms (e.g., proper nouns) from the target location name once.
    # These terms will be used to filter out overly similar candidates.
    extracted_terms_from_target = extract_named_entities_and_proper_nouns(target_location_name, nlp_processor)
    logging.debug(f"Extracted terms from target '{target_location_name}' for filtering: {extracted_terms_from_target}")

    while current_k <= max_k:
        # Get K semantically similar locations
        # The `target_location_name` itself is used for semantic query.
        semantically_similar_locations, semantic_similarity_scores = query_similar_locations(
            target_location_name, embedding_model, nn_search_model, all_location_names, top_k=current_k
        )

        # Apply get_main_name to each similar location if names have "Name / Details" format
        processed_similar_locations = [get_main_name(loc) for loc in semantically_similar_locations]
        logging.debug(f"Retrieved top {current_k} semantic locations (processed): {processed_similar_locations}")

        # Filter these locations
        # `filter_locations` removes exact semantic matches (score=1) and those containing target's specific terms
        current_filtered_locations = filter_locations(
            processed_similar_locations,
            semantic_similarity_scores,
            extracted_terms_from_target
        )
        logging.debug(f"Filtered locations at k={current_k}: {current_filtered_locations}")

        # If we have enough matches, store them and break
        if len(current_filtered_locations) >= min_matches:
            final_filtered_locations = current_filtered_locations
            break

        # If this is the last attempt (current_k will exceed max_k in next iteration)
        # and we still have *some* results, use them.
        if current_k + step_size > max_k and current_filtered_locations:
            final_filtered_locations = current_filtered_locations
            logging.info(f"Max k reached. Using {len(final_filtered_locations)} found matches with k={current_k}.")
            break

        # Increase k for the next iteration
        current_k += step_size

        if current_k <= max_k:
            logging.info(
                f"Insufficient matches ({len(current_filtered_locations)} < {min_matches}) found with k={current_k - step_size}. "
                f"Expanding search to k={current_k}")
        else:  # current_k has now exceeded max_k
            # If loop finishes, it means not enough matches were found even with max_k
            # If current_filtered_locations is not empty, it means we stored them above.
            # If it IS empty, then final_filtered_locations is also empty.
            if not final_filtered_locations:  # only log warning if truly no results
                final_filtered_locations = current_filtered_locations  # Save what we have from last attempt
                logging.warning(f"Could not find {min_matches} matches even with k={max_k}. "
                                f"Proceeding with {len(final_filtered_locations)} matches.")

    if not final_filtered_locations and current_k > max_k:  # If loop ended because max_k was passed and no matches were found
        logging.warning(f"Could not find {min_matches} matches. Max k ({max_k}) reached. No suitable locations found.")

    return final_filtered_locations, min(current_k, max_k)  # Return the k value that was actually used or max_k


def get_location_surrogate(
        target_location_query,
        embedding_model,
        nn_search_model,
        nlp_processor,
        all_location_names,
        initial_k=20,
        max_k=100,
        min_matches=20,
        temperature_for_sampling=0.1
):
    """
    Main function to find and sample a surrogate location using an adaptive search strategy.

    Parameters
    ----------
    target_location_query : str
        The name or description of the target location to find a surrogate for.
    embedding_model
        The embedding model.
    nn_search_model
        The nearest neighbor model.
    nlp_processor
        A spaCy language model instance.
    all_location_names : list
        List of all available location names in the dataset.
    initial_k : int
        Initial number of semantic neighbors to retrieve.
    max_k : int
        Maximum number of semantic neighbors to consider.
    min_matches : int
        Minimum number of filtered locations required after adaptive search.
    temperature_for_sampling : float
        Temperature for calculating probabilities for sampling.

    Returns
    -------
    tuple
        A tuple containing:
        - sampled_location : str or None
            The selected surrogate location name, or None if no suitable location is found.
        - probabilities : numpy.ndarray
            An array of probabilities associated with the locations considered for sampling.
        - candidate_locations : tuple
            A tuple of location names that were candidates for sampling.
        - k_used : int
            The final value of `k` (number of semantic neighbors) used in the adaptive search.
    """
    # 1. Clean the input target location query
    cleaned_target_location = remove_non_alphanumeric(target_location_query)
    if not cleaned_target_location:
        logging.error("Target location query is empty after cleaning.")
        return None, np.array([]), (), 0

    # 2. Adaptively query for similar locations
    #    - `query_similar_locations_adaptive` handles semantic search, main name extraction, and filtering.
    filtered_similar_locations, k_used = query_similar_locations_adaptive(
        cleaned_target_location, embedding_model, nn_search_model, nlp_processor,
        all_location_names, initial_k=initial_k, max_k=max_k, min_matches=min_matches
    )

    logging.debug(f"Filtered similar locations for ranking: {filtered_similar_locations}")

    if not filtered_similar_locations:
        logging.warning("No suitable similar locations found after adaptive querying and filtering.")
        return None, np.array([]), (), k_used

    # 3. Rank these filtered locations by keyword similarity to the original cleaned target
    #    - `rank_locations_by_keyword_similarity` uses Levenshtein-based term similarity
    #      and then takes the top 50% contributors by score.
    ranked_locations_with_scores = rank_locations_by_keyword_similarity(
        cleaned_target_location,
        filtered_similar_locations
    )
    logging.debug(f"Ranked locations with scores: {ranked_locations_with_scores}")

    if not ranked_locations_with_scores:
        logging.warning("No locations remained after ranking by keyword similarity.")
        return None, np.array([]), (), k_used

    # 4. Calculate sampling probabilities for the ranked locations
    candidate_locations, probabilities = calculate_location_probabilities(
        ranked_locations_with_scores,
        temperature=temperature_for_sampling
    )
    logging.debug(f"Candidate locations for sampling: {candidate_locations}")
    logging.debug(f"Probabilities for sampling: {probabilities}")

    if not candidate_locations or probabilities.size == 0 or np.sum(probabilities) == 0:
        logging.warning("No valid candidates or probabilities for sampling.")
        # Fallback: if probabilities are all zero, try uniform choice from candidates if any
        if candidate_locations:
            logging.info("Probabilities were zero, attempting uniform choice from candidates.")
            sampled_location = np.random.choice(candidate_locations)
            return sampled_location, np.full(len(candidate_locations),
                                             1 / len(candidate_locations)), candidate_locations, k_used
        return None, np.array([]), (), k_used

    # 5. Sample a surrogate location based on these probabilities
    try:
        sampled_location = np.random.choice(candidate_locations, p=probabilities)
    except ValueError as e:
        logging.error(f"Error during sampling: {e}. Probabilities sum: {np.sum(probabilities)}")
        # Fallback if np.random.choice fails (e.g. probabilities don't sum to 1 due to float precision)
        # Pick the one with the highest score from ranked_locations_with_scores
        if ranked_locations_with_scores:
            sampled_location = ranked_locations_with_scores[0][0]  # Top ranked
            logging.info(f"Sampling failed, falling back to highest ranked: {sampled_location}")
        else:
            sampled_location = None

    return sampled_location, probabilities, candidate_locations, k_used
