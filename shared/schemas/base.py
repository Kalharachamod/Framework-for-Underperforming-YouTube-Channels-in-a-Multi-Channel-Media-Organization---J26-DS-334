"""Field types and tabular conversion shared by all research schemas."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Annotated, Any, ClassVar

import pandas as pd
import pyarrow as pa
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

# Bump when a field is renamed, removed or changes type (see docs/architecture/schemas.md).
SCHEMA_VERSION = "1.3"  # 1.1 Channel.description/published_at; 1.2 Video.duration_seconds;
                        # 1.3 Comment.parent_comment_id/edited_at (all optional)


def _reject_bool(value: Any) -> Any:
    # bool is a subclass of int; True must not silently become a count of 1.
    if isinstance(value, bool):
        raise ValueError("expected an integer count, got a boolean")
    return value


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _clean_tags(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError("tags must be a list of strings")
    if not all(isinstance(tag, str) for tag in value):
        raise ValueError("every tag must be a string")
    return [tag.strip() for tag in value if tag.strip()]


# YouTube IDs use letters, digits, '-' and '_'; reply comment IDs also contain '.'.
YouTubeId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-]+$"),
]
Count = Annotated[int, BeforeValidator(_reject_bool), Field(ge=0)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
Tags = Annotated[list[str], BeforeValidator(_clean_tags)]

# pandas dtypes that give every column a fixed Parquet type, even when all values are null.
STRING = "string"
INT = "Int64"
TIMESTAMP = "datetime64[us, UTC]"
STRING_LIST = pd.ArrowDtype(pa.list_(pa.string()))


class ResearchRecord(BaseModel):
    """Base class for shared research records: immutable, no unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Column name -> pandas dtype, in Parquet column order. Set by each subclass.
    DTYPES: ClassVar[dict[str, Any]] = {}

    def to_record(self) -> dict[str, Any]:
        """Plain Python dict (datetimes stay datetime objects) for pandas/Parquet."""
        return self.model_dump()

    def to_json_dict(self) -> dict[str, Any]:
        """JSON-safe dict (ISO-8601 timestamps), e.g. for future API responses."""
        return self.model_dump(mode="json")


def to_dataframe(records: Iterable[ResearchRecord], model: type[ResearchRecord]) -> pd.DataFrame:
    """Convert validated records into a typed DataFrame ready for ``write_dataset``.

    Column order and dtypes come from ``model.DTYPES``, so every snapshot of the
    same entity produces the same Parquet schema.
    """
    rows = []
    for record in records:
        if not isinstance(record, model):
            raise TypeError(f"expected {model.__name__}, got {type(record).__name__}")
        rows.append(record.to_record())

    columns = list(model.DTYPES)
    df = pd.DataFrame(rows, columns=columns)
    return df.astype(model.DTYPES)
