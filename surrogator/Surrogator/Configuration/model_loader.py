import spacy
from sentence_transformers import SentenceTransformer

from Surrogator.Configuration.const import EMBEDDING_MODEL_NAME
from Surrogator.Configuration.const import EMBEDDING_MODEL_LOCAL_COPY
from Surrogator.Configuration.const import SPACY_MODEL


def load_embedding_model() -> SentenceTransformer:
    """
    load or download model for SentencesTransformers used in fictive mode of surrogator
    """

    if not EMBEDDING_MODEL_LOCAL_COPY.exists():
        download_models()

    return SentenceTransformer(str(EMBEDDING_MODEL_LOCAL_COPY))


def download_models() -> None:
    """
    download or load spaCy based language model used in fictive mode of surrogator
    """
    spacy.cli.download(SPACY_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    model.save(str(EMBEDDING_MODEL_LOCAL_COPY))
