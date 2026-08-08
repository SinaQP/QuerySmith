"""Physical SQL Server catalog metadata and type normalization."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querysmith.models import RelationshipSpec, TableRef


@dataclass(frozen=True)
class CatalogColumn:
    """Physical metadata read from ``sys.columns`` and ``sys.types``."""

    name: str
    data_type: str
    nullable: bool
    primary_key: bool = False
    length: int | None = None
    precision: int | None = None
    scale: int | None = None

    @property
    def identity_key(self) -> str:
        return self.name.casefold()


@dataclass(frozen=True)
class CatalogTable:
    """One discovered physical table and all of its columns."""

    ref: TableRef
    columns: Collection[CatalogColumn] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", tuple(self.columns))

    def get_column(self, name: str) -> CatalogColumn | None:
        key = name.casefold()
        return next(
            (column for column in self.columns if column.identity_key == key), None
        )


@dataclass(frozen=True)
class CatalogSnapshot:
    """Bounded catalog result for an exact set of requested tables."""

    requested_refs: Collection[TableRef]
    tables: Collection[CatalogTable]
    relationships: Collection[RelationshipSpec] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_refs", tuple(self.requested_refs))
        object.__setattr__(self, "tables", tuple(self.tables))
        object.__setattr__(self, "relationships", tuple(self.relationships))

    def get_table(self, ref: TableRef) -> CatalogTable | None:
        return next((table for table in self.tables if table.ref == ref), None)


_TYPE_PATTERN = re.compile(r"^\s*([a-zA-Z0-9_]+)\s*(?:\(\s*([^)]*)\s*\))?\s*$")
_TYPE_ALIASES = {
    "integer": "int",
    "numeric": "decimal",
    "rowversion": "timestamp",
}


@dataclass(frozen=True)
class NormalizedType:
    """Canonical developer/catalog type declaration."""

    base: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


def normalize_type(
    data_type: str,
    *,
    length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
) -> NormalizedType:
    """Normalize SQL Server base names and optional size parameters."""

    match = _TYPE_PATTERN.fullmatch(data_type)
    if match is None:
        return NormalizedType(data_type.strip().casefold(), length, precision, scale)
    base = _TYPE_ALIASES.get(match.group(1).casefold(), match.group(1).casefold())
    arguments = match.group(2)
    if arguments and length is None and precision is None and scale is None:
        values = [value.strip().casefold() for value in arguments.split(",")]
        try:
            if len(values) == 1:
                length = -1 if values[0] == "max" else int(values[0])
            elif len(values) == 2:
                precision, scale = int(values[0]), int(values[1])
        except ValueError:
            return NormalizedType(data_type.strip().casefold())
    return NormalizedType(base, length, precision, scale)


def types_compatible(declared: NormalizedType, physical: NormalizedType) -> bool:
    """Conservatively compare declared metadata with physical metadata."""

    if declared.base != physical.base:
        return False
    for expected, actual in (
        (declared.length, physical.length),
        (declared.precision, physical.precision),
        (declared.scale, physical.scale),
    ):
        if expected is not None and expected != actual:
            return False
    return True


def relationship_types_compatible(left: CatalogColumn, right: CatalogColumn) -> bool:
    """Require matching normalized physical types for relationship endpoints."""

    return normalize_type(
        left.data_type,
        length=left.length,
        precision=left.precision,
        scale=left.scale,
    ) == normalize_type(
        right.data_type,
        length=right.length,
        precision=right.precision,
        scale=right.scale,
    )


def format_type(
    data_type: str,
    *,
    length: int | None,
    precision: int | None,
    scale: int | None,
) -> str:
    """Render physical type metadata for prompt serialization."""

    base = data_type.casefold()
    if base in {"char", "varchar", "binary", "varbinary"} and length is not None:
        return f"{data_type}({'max' if length == -1 else length})"
    if base in {"nchar", "nvarchar"} and length is not None:
        size = "max" if length == -1 else length
        return f"{data_type}({size})"
    if base in {"decimal", "numeric"} and precision is not None and scale is not None:
        return f"{data_type}({precision},{scale})"
    return data_type
