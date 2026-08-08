"""Developer-owned semantic catalog models and validation."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querysmith.models import QuerySpace, TableRef

_MAX_SYNONYMS = 12
_MAX_EXAMPLES = 3
_MAX_TEXT_LENGTH = 1000
_MAX_TERM_LENGTH = 120


class SemanticCatalogError(ValueError):
    """Base class for invalid semantic metadata."""


class SemanticValidationError(SemanticCatalogError):
    """Raised when semantic metadata is malformed or references invalid data."""


class SemanticTypeMismatchError(SemanticCatalogError):
    """Raised when a semantic type is incompatible with its SQL type."""


class SynonymConflictError(SemanticCatalogError):
    """Raised when semantic names are ambiguous."""


class CapabilityConflictError(SemanticCatalogError):
    """Raised when access policy and operation capabilities conflict."""


class BusinessRuleValidationError(SemanticCatalogError):
    """Raised when a business rule references unavailable metadata."""


class ContextBuildError(SemanticCatalogError):
    """Raised when deterministic LLM context cannot be built."""


class SemanticType(str, Enum):
    TEXT = "text"
    IDENTIFIER = "identifier"
    CURRENCY = "currency"
    QUANTITY = "quantity"
    PERCENTAGE = "percentage"
    DATE = "date"
    DATETIME = "datetime"
    DURATION = "duration"
    BOOLEAN = "boolean"
    CATEGORY = "category"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    ADDRESS = "address"
    PERSON_NAME = "person_name"
    SENSITIVE_IDENTIFIER = "sensitive_identifier"


class DataSensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class RuleEnforcement(str, Enum):
    ADVISORY = "advisory"


@dataclass(frozen=True)
class ColumnCapabilities:
    """Operation-specific permissions enforced by the SQL guard."""

    selectable: bool = True
    filterable: bool = True
    sortable: bool = True
    groupable: bool = True
    aggregatable: bool = True
    joinable: bool = True

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, bool):
                raise SemanticValidationError(f"capability {name} must be a bool.")

    @classmethod
    def denied(cls) -> ColumnCapabilities:
        return cls(False, False, False, False, False, False)

    @property
    def any_enabled(self) -> bool:
        return any(self.__dict__.values())

    def allows(self, operation: str) -> bool:
        attribute = {
            "SELECT": "selectable",
            "FILTER": "filterable",
            "SORT": "sortable",
            "GROUP": "groupable",
            "AGGREGATE": "aggregatable",
            "JOIN": "joinable",
        }.get(operation.upper())
        return bool(attribute and getattr(self, attribute))

    @property
    def allowed_operations(self) -> tuple[str, ...]:
        return tuple(
            operation
            for operation in ("SELECT", "FILTER", "SORT", "GROUP", "AGGREGATE", "JOIN")
            if self.allows(operation)
        )


@dataclass(frozen=True)
class BusinessRule:
    """An advisory semantic instruction with validated references."""

    description: str
    applies_to: TableRef | None = None
    applies_to_columns: Collection[str] = field(default_factory=tuple)
    enforcement: RuleEnforcement = RuleEnforcement.ADVISORY

    def __post_init__(self) -> None:
        from querysmith.models import TableRef

        object.__setattr__(
            self, "description", _text(self.description, "business rule")
        )
        object.__setattr__(
            self,
            "applies_to_columns",
            _terms(self.applies_to_columns, "business rule column", limit=20),
        )
        if self.applies_to is not None and not isinstance(self.applies_to, TableRef):
            raise BusinessRuleValidationError(
                "business rule applies_to must be a TableRef or None."
            )
        if not isinstance(self.enforcement, RuleEnforcement):
            try:
                object.__setattr__(
                    self, "enforcement", RuleEnforcement(self.enforcement)
                )
            except ValueError as error:
                raise BusinessRuleValidationError(
                    "Unsupported rule enforcement."
                ) from error


@dataclass(frozen=True)
class SemanticColumnSpec:
    """Semantic metadata bound to one physical column identity."""

    table: TableRef
    column: str
    description: str | None = None
    alias: str | None = None
    synonyms: Collection[str] = field(default_factory=tuple)
    semantic_type: SemanticType | str | None = None
    unit: str | None = None
    example_values: Collection[str] = field(default_factory=tuple)
    capabilities: ColumnCapabilities | None = None
    interpretation_warnings: Collection[str] = field(default_factory=tuple)
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC

    def __post_init__(self) -> None:
        from querysmith.models import TableRef

        if not isinstance(self.table, TableRef):
            raise SemanticValidationError("semantic column table must be a TableRef.")
        object.__setattr__(self, "column", _term(self.column, "semantic column"))
        object.__setattr__(
            self, "description", _optional_text(self.description, "column description")
        )
        object.__setattr__(self, "alias", _optional_term(self.alias, "column alias"))
        object.__setattr__(
            self, "synonyms", _terms(self.synonyms, "column synonym", _MAX_SYNONYMS)
        )
        object.__setattr__(self, "unit", _optional_term(self.unit, "unit"))
        object.__setattr__(
            self,
            "example_values",
            _terms(self.example_values, "example value", _MAX_EXAMPLES),
        )
        object.__setattr__(
            self,
            "interpretation_warnings",
            _texts(self.interpretation_warnings, "interpretation warning", 10),
        )
        if self.semantic_type is not None and not isinstance(
            self.semantic_type, SemanticType
        ):
            value = _term(self.semantic_type, "semantic type").casefold()
            try:
                object.__setattr__(self, "semantic_type", SemanticType(value))
            except ValueError as error:
                raise SemanticValidationError(
                    f"Unsupported semantic type {value!r}."
                ) from error
        if self.capabilities is not None and not isinstance(
            self.capabilities, ColumnCapabilities
        ):
            raise SemanticValidationError(
                "capabilities must be ColumnCapabilities or None."
            )
        if not isinstance(self.sensitivity, DataSensitivity):
            try:
                object.__setattr__(
                    self, "sensitivity", DataSensitivity(self.sensitivity)
                )
            except ValueError as error:
                raise SemanticValidationError(
                    "Unsupported sensitivity classification."
                ) from error

    @property
    def identity_key(self) -> tuple[tuple[str, str], str]:
        return (self.table.identity_key, self.column.casefold())


@dataclass(frozen=True)
class SemanticTableSpec:
    """Business meaning for one physical table."""

    ref: TableRef
    entity_name: str | None = None
    description: str | None = None
    synonyms: Collection[str] = field(default_factory=tuple)
    business_rules: Collection[BusinessRule] = field(default_factory=tuple)
    interpretation_warnings: Collection[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        from querysmith.models import TableRef

        if not isinstance(self.ref, TableRef):
            raise SemanticValidationError("semantic table ref must be a TableRef.")
        object.__setattr__(
            self, "entity_name", _optional_term(self.entity_name, "entity name")
        )
        object.__setattr__(
            self, "description", _optional_text(self.description, "table description")
        )
        object.__setattr__(
            self, "synonyms", _terms(self.synonyms, "table synonym", _MAX_SYNONYMS)
        )
        rules: list[BusinessRule] = []
        for rule in self.business_rules:
            rules.append(
                rule
                if isinstance(rule, BusinessRule)
                else BusinessRule(str(rule), self.ref)
            )
        object.__setattr__(self, "business_rules", tuple(rules))
        object.__setattr__(
            self,
            "interpretation_warnings",
            _texts(self.interpretation_warnings, "interpretation warning", 10),
        )


@dataclass(frozen=True)
class SemanticCatalog:
    """Immutable developer semantic metadata, separate from physical catalog data."""

    tables: Collection[SemanticTableSpec] = field(default_factory=tuple)
    columns: Collection[SemanticColumnSpec] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tables", tuple(self.tables))
        object.__setattr__(self, "columns", tuple(self.columns))
        table_keys: set[tuple[str, str]] = set()
        for table in self.tables:
            if table.ref.identity_key in table_keys:
                raise SemanticValidationError(
                    f"Duplicate semantic table {table.ref.full_name}."
                )
            table_keys.add(table.ref.identity_key)
        column_keys: set[tuple[tuple[str, str], str]] = set()
        for column in self.columns:
            if column.identity_key in column_keys:
                raise SemanticValidationError(
                    f"Duplicate semantic column {column.table.full_name}.{column.column}."
                )
            column_keys.add(column.identity_key)

    @classmethod
    def from_query_space(cls, query_space: QuerySpace) -> SemanticCatalog:
        tables: list[SemanticTableSpec] = []
        columns: list[SemanticColumnSpec] = []
        for table in query_space.tables:
            tables.append(
                SemanticTableSpec(
                    ref=table.ref,
                    entity_name=table.alias,
                    description=table.description,
                    synonyms=table.synonyms,
                    business_rules=tuple(
                        rule
                        for rule in table.business_rules
                        if isinstance(rule, BusinessRule)
                    ),
                    interpretation_warnings=table.interpretation_warnings,
                )
            )
            columns.extend(
                SemanticColumnSpec(
                    table=table.ref,
                    column=column.name,
                    description=column.description,
                    alias=column.alias,
                    synonyms=column.synonyms,
                    semantic_type=column.semantic_type,
                    unit=column.unit,
                    example_values=column.example_values,
                    capabilities=column.capabilities,
                    interpretation_warnings=column.interpretation_warnings,
                    sensitivity=column.sensitivity,
                )
                for column in table.columns
            )
        return cls(tables, columns)

    def get_table(self, ref: TableRef) -> SemanticTableSpec | None:
        return next((table for table in self.tables if table.ref == ref), None)

    def get_column(self, ref: TableRef, name: str) -> SemanticColumnSpec | None:
        key = name.casefold()
        return next(
            (
                column
                for column in self.columns
                if column.table == ref and column.column.casefold() == key
            ),
            None,
        )


def _term(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise SemanticValidationError(f"{label} must be a string.")
    normalized = " ".join(value.split())
    if not normalized:
        raise SemanticValidationError(f"{label} cannot be empty.")
    if "\x00" in normalized or len(normalized) > _MAX_TERM_LENGTH:
        raise SemanticValidationError(f"{label} is invalid or too long.")
    return normalized


def _text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise SemanticValidationError(f"{label} must be a string.")
    normalized = " ".join(value.split())
    if not normalized:
        raise SemanticValidationError(f"{label} cannot be empty.")
    if "\x00" in normalized or len(normalized) > _MAX_TEXT_LENGTH:
        raise SemanticValidationError(f"{label} is invalid or too long.")
    return normalized


def _optional_term(value: str | None, label: str) -> str | None:
    return None if value is None else _term(value, label)


def _optional_text(value: str | None, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _terms(values: Collection[str], label: str, limit: int) -> tuple[str, ...]:
    if len(values) > limit:
        raise SemanticValidationError(
            f"{label}s cannot contain more than {limit} values."
        )
    normalized = tuple(_term(value, label) for value in values)
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise SynonymConflictError(f"Duplicate {label} values are not allowed.")
    return normalized


def _texts(values: Collection[str], label: str, limit: int) -> tuple[str, ...]:
    if len(values) > limit:
        raise SemanticValidationError(
            f"{label}s cannot contain more than {limit} values."
        )
    normalized = tuple(_text(value, label) for value in values)
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise SemanticValidationError(f"Duplicate {label} values are not allowed.")
    return normalized
