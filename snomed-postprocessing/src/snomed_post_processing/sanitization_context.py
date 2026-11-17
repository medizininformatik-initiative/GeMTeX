import pandas as pd


def masked_overview_csv(overview_df: pd.DataFrame) -> bytes:
    masked = overview_df.copy()
    for column, prefix in (("Document", "document"), ("Annotator", "annotator")):
        aliases = {name: f"{prefix}-{index}" for index, name in enumerate(masked[column].unique(), start=1)}
        masked[column] = masked[column].map(aliases)
    return masked.to_csv(index=False).encode("utf-8-sig")