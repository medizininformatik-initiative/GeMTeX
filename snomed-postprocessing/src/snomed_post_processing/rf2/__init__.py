"""Backward-compatible alias for :mod:`snomed_post_processing.release_ingestion`.

The implementation moved to ``release_ingestion`` because it is more descriptive
for users who are not familiar with the SNOMED CT RF2 abbreviation.
"""

from ..release_ingestion import *  # noqa: F401,F403
