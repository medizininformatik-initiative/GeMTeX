from pathlib import Path

"""
    Configuration of paths of models and external resources.
"""

_THIS_DIR = Path(__file__).parent
_RESSOURCE_DIR = _THIS_DIR.parent.parent / 'resources'

HOSPITAL_DATA_PATH = _RESSOURCE_DIR / 'Location_Lists' / 'Combined_healthcare_facilities.txt'
HOSPITAL_NEAREST_NEIGHBORS_MODEL_PATH = _RESSOURCE_DIR / 'model' / 'nearest_neighbors_model_location_hospital.joblib'

ORGANIZATION_DATA_PATH = _RESSOURCE_DIR / 'Location_Lists' / 'organizations_office_craft_club_industrial.txt'
ORGANIZATION_NEAREST_NEIGHBORS_MODEL_PATH = _RESSOURCE_DIR / 'model' \
    / 'nearest_neighbors_model_location_organization.joblib'

OTHER_DATA_PATH = _RESSOURCE_DIR / 'Location_Lists' / 'location_other_osm_primary_map_features.txt'
OTHER_NEAREST_NEIGHBORS_MODEL_PATH = _RESSOURCE_DIR / 'model' / 'nearest_neighbors_model_location_other.joblib'

EMBEDDING_MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
EMBEDDING_MODEL_LOCAL_COPY = _RESSOURCE_DIR / 'model' / 'paraphrase-multilingual-MiniLM-L12-v2'
SPACY_MODEL = 'de_core_news_lg'

PHONE_AREA_CODE_PATH = _RESSOURCE_DIR / 'phone' / 'tel_numbers_merged.json'