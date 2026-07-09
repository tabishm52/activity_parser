"""Shared DataFrame/Series refinements, used by both TCX/GPX and FIT parsing."""

import pandas as pd


def coerce_numeric_all_or_nothing(values: pd.Series) -> pd.Series:
    """Coerces ``values`` to numeric only if every non-null value parses.

    If any originally-non-null value fails to parse as numeric, returns ``values``
    unchanged rather than partially coercing the column.
    """
    non_null = values.notna().sum()
    if non_null == 0:
        return values

    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() != non_null:
        return values

    return numeric


def index_by_time(records: pd.DataFrame, column: str) -> pd.DataFrame:
    """Sets ``column`` as the index, dropping rows with no timestamp or a duplicate one.

    If ``column`` is entirely absent (no row has any clock data at all, e.g. a GPX
    route with no ``<time>`` elements) but rows exist, they're kept under their
    original index rather than all being dropped as "missing".
    """
    if column not in records.columns:
        if not records.empty:
            return records.rename_axis(column)
        records[column] = pd.NaT

    records = records.set_index(column)
    records = records[records.index.notna()]
    return records[~records.index.duplicated()]
