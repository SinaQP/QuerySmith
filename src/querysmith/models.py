"""Schema, catalog, and query-space domain models for QuerySmith."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from querysmith.catalog import CatalogColumn, CatalogTable
from querysmith.semantic import (
    BusinessRule,
    CapabilityConflictError,
    ColumnCapabilities,
    DataSensitivity,
    SemanticColumnSpec,
    SemanticTableSpec,
    SemanticType,
    SemanticValidationError,
    SynonymConflictError,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine


class QuerySpaceError(ValueError):
    """Base class for invalid QuerySpace operations."""

    code: Any = None


class QuerySpaceValidationError(QuerySpaceError):
    """Raised when QuerySpace metadata is internally inconsistent."""


class QuerySpaceLookupError(QuerySpaceError, KeyError):
    """Raised when a table or column is not present in a QuerySpace."""


class CatalogResolutionError(QuerySpaceError):
    """Base class for failures while resolving developer intent."""


class TableNotFoundError(CatalogResolutionError):
    """Raised when a requested physical table does not exist."""


class ColumnNotFoundError(CatalogResolutionError):
    """Raised when a declared physical column does not exist."""


class ColumnTypeMismatchError(CatalogResolutionError):
    """Raised when declared and catalog column types are incompatible."""


class AliasConflictError(CatalogResolutionError):
    """Raised when semantic aliases are ambiguous."""


class ForbiddenColumnError(CatalogResolutionError):
    """Raised when a denied column is referenced by developer intent."""


class RelationshipResolutionError(CatalogResolutionError):
    """Raised when a manual relationship cannot be resolved safely."""


class DefaultColumnPolicy(str, Enum):
    """Policy for physical columns omitted from a developer QuerySpace."""

    DENY = "deny"
    ALLOW = "allow"


class ColumnAccessLevel(str, Enum):
    """Whether a physical column is available to generated SQL or policies."""

    USER_ALLOWED = "user_allowed"
    POLICY_ONLY = "policy_only"
    DENIED = "denied"


@dataclass(frozen=True)
class AccessProfile:
    """A named security profile defining host-application access levels."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise QuerySpaceValidationError(
                "access profile name must be a non-empty string."
            )
        if "\x00" in self.name:
            raise QuerySpaceValidationError(
                "access profile name cannot contain a null byte."
            )
        object.__setattr__(self, "name", self.name.strip())

    @property
    def identity_key(self) -> str:
        return self.name.casefold()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AccessProfile):
            return self.identity_key == other.identity_key
        if isinstance(other, str):
            return self.identity_key == other.strip().casefold()
        return False

    def __hash__(self) -> int:
        return hash(self.identity_key)


class ResultAccess(str, Enum):
    """Output exposure policy for a column in a query result set."""

    VISIBLE = "visible"
    HIDDEN = "hidden"
    MASKED = "masked"


class MaskingMode(str, Enum):
    """Supported transformation modes for redacting column values."""

    FULL = "full"
    PARTIAL = "partial"
    CONSTANT = "constant"


@dataclass(frozen=True)
class MaskingPolicy:
    """Rules for redacting sensitive column values before result delivery."""

    mode: MaskingMode | str = MaskingMode.FULL
    visible_prefix: int = 0
    visible_suffix: int = 4
    mask_character: str = "*"
    replacement: str = "********"

    def __post_init__(self) -> None:
        if not isinstance(self.mode, MaskingMode):
            try:
                object.__setattr__(self, "mode", MaskingMode(self.mode))
            except ValueError as error:
                raise QuerySpaceValidationError(
                    f"Invalid masking mode {self.mode!r}"
                ) from error
        if (
            not isinstance(self.visible_prefix, int)
            or isinstance(self.visible_prefix, bool)
            or self.visible_prefix < 0
            or not isinstance(self.visible_suffix, int)
            or isinstance(self.visible_suffix, bool)
            or self.visible_suffix < 0
        ):
            raise QuerySpaceValidationError(
                "Masking visible prefix and suffix must be non-negative ints."
            )
        if not isinstance(self.mask_character, str) or len(self.mask_character) != 1:
            raise QuerySpaceValidationError(
                "Mask character must be a single character string."
            )
        if not isinstance(self.replacement, str):
            raise QuerySpaceValidationError("Masking replacement must be a string.")

    @classmethod
    def full(cls, replacement: str = "********") -> MaskingPolicy:
        return cls(mode=MaskingMode.FULL, replacement=replacement)

    @classmethod
    def partial(
        cls,
        visible_prefix: int = 0,
        visible_suffix: int = 4,
        mask_character: str = "*",
    ) -> MaskingPolicy:
        return cls(
            mode=MaskingMode.PARTIAL,
            visible_prefix=visible_prefix,
            visible_suffix=visible_suffix,
            mask_character=mask_character,
        )

    @classmethod
    def partial_suffix(
        cls, suffix_length: int = 4, mask_character: str = "*"
    ) -> MaskingPolicy:
        return cls(
            mode=MaskingMode.PARTIAL,
            visible_prefix=0,
            visible_suffix=suffix_length,
            mask_character=mask_character,
        )

    @classmethod
    def partial_prefix(
        cls, prefix_length: int = 3, mask_character: str = "*"
    ) -> MaskingPolicy:
        return cls(
            mode=MaskingMode.PARTIAL,
            visible_prefix=prefix_length,
            visible_suffix=0,
            mask_character=mask_character,
        )

    @classmethod
    def constant(cls, value: str = "[REDACTED]") -> MaskingPolicy:
        return cls(mode=MaskingMode.CONSTANT, replacement=value)


@dataclass(frozen=True)
class ColumnAccess:
    """Profile-specific access control settings for a column."""

    selectable: bool = True
    filterable: bool = True
    sortable: bool = True
    groupable: bool = True
    aggregatable: bool = True
    joinable: bool = True
    result_access: ResultAccess | str = ResultAccess.VISIBLE
    capabilities: ColumnCapabilities | None = None
    masking: MaskingPolicy | None = None

    USER_ALLOWED: ClassVar[ColumnAccessLevel] = ColumnAccessLevel.USER_ALLOWED
    POLICY_ONLY: ClassVar[ColumnAccessLevel] = ColumnAccessLevel.POLICY_ONLY
    DENIED: ClassVar[ColumnAccessLevel] = ColumnAccessLevel.DENIED

    def __post_init__(self) -> None:
        if not isinstance(self.result_access, ResultAccess):
            try:
                object.__setattr__(
                    self, "result_access", ResultAccess(self.result_access)
                )
            except ValueError as error:
                raise QuerySpaceValidationError(
                    f"Invalid result access {self.result_access!r}"
                ) from error
        if self.capabilities is None:
            caps = ColumnCapabilities(
                selectable=self.selectable,
                filterable=self.filterable,
                sortable=self.sortable,
                groupable=self.groupable,
                aggregatable=self.aggregatable,
                joinable=self.joinable,
            )
            object.__setattr__(self, "capabilities", caps)

    @classmethod
    def allow(
        cls, result_access: ResultAccess | str = ResultAccess.VISIBLE
    ) -> ColumnAccess:
        return cls(
            selectable=True,
            filterable=True,
            sortable=True,
            groupable=True,
            aggregatable=True,
            joinable=True,
            result_access=result_access,
        )

    @classmethod
    def deny(cls) -> ColumnAccess:
        return cls(
            selectable=False,
            filterable=False,
            sortable=False,
            groupable=False,
            aggregatable=False,
            joinable=False,
            result_access=ResultAccess.HIDDEN,
        )


@dataclass(frozen=True)
class TableAccess:
    """Profile-specific table availability settings."""

    available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise QuerySpaceValidationError("TableAccess available must be a bool.")


class FilterOperator(str, Enum):
    """Closed set of operators supported by mandatory filter injection."""

    EQ = "="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    IN = "IN"

    @classmethod
    def _missing_(cls, value: object) -> FilterOperator | None:
        if isinstance(value, str):
            val_upper = value.upper().strip()
            if val_upper in ("NOT_EQ", "NOT_EQUAL", "NE", "<>"):
                return cls.NE
            if val_upper in ("EQ", "EQUAL", "="):
                return cls.EQ
            if val_upper in ("IN",):
                return cls.IN
            if val_upper in ("GT", ">"):
                return cls.GT
            if val_upper in ("GTE", ">="):
                return cls.GTE
            if val_upper in ("LT", "<"):
                return cls.LT
            if val_upper in ("LTE", "<="):
                return cls.LTE
        return None


@dataclass(frozen=True)
class RequiredFilter:
    """A parameterized mandatory row-level policy filter resolved from runtime context."""

    table: TableRef | None = None
    column: str = ""
    operator: FilterOperator | str = FilterOperator.EQ
    value_from_context: str | None = None
    value: object | None = None

    def __post_init__(self) -> None:
        if self.table is not None and not isinstance(self.table, TableRef):
            raise QuerySpaceValidationError(
                "RequiredFilter table must be a TableRef or None."
            )
        _validated_identifier(self.column, "RequiredFilter column")
        if not isinstance(self.operator, FilterOperator):
            try:
                object.__setattr__(self, "operator", FilterOperator(self.operator))
            except ValueError as error:
                raise QuerySpaceValidationError(
                    "RequiredFilter operator is not supported."
                ) from error
        if self.value_from_context is not None:
            _validated_identifier(
                self.value_from_context, "RequiredFilter value_from_context"
            )
        if self.value_from_context is None and self.value is None:
            raise QuerySpaceValidationError(
                "RequiredFilter requires either value_from_context or value."
            )


@dataclass(frozen=True)
class ProjectionColumn:
    """Metadata describing one column in the authorized output projection."""

    output_name: str
    source_table: TableRef | None
    source_column: str | None
    result_access: ResultAccess = ResultAccess.VISIBLE
    masking_policy: MaskingPolicy | None = None
    is_expression: bool = False
    leaf_columns: tuple[tuple[TableRef, str], ...] = ()


class JoinType(str, Enum):
    """Join shapes that can be explicitly enabled by an execution policy."""

    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"
    CROSS = "cross"
    APPLY = "apply"


def _validated_identifier(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise QuerySpaceValidationError(f"{label} must be a string.")
    if not value.strip():
        raise QuerySpaceValidationError(f"{label} cannot be empty.")
    if "\x00" in value:
        raise QuerySpaceValidationError(f"{label} cannot contain a null byte.")
    return value


def _optional_identifier(value: str | None, label: str) -> str | None:
    return None if value is None else _validated_identifier(value, label)


def _identifier_key(value: str) -> str:
    """Match the case-insensitive identifier behavior used by SQL Server."""

    return value.casefold()


def _semantic_terms(
    values: Collection[str],
    label: str,
    limit: int,
    *,
    max_length: int = 120,
) -> tuple[str, ...]:
    if len(values) > limit:
        raise SemanticValidationError(
            f"{label}s cannot contain more than {limit} values."
        )
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise SemanticValidationError(f"{label} must be a string.")
        term = " ".join(value.split())
        if not term or "\x00" in term or len(term) > max_length:
            raise SemanticValidationError(f"{label} is invalid or too long.")
        normalized.append(term)
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise SynonymConflictError(f"Duplicate {label} values are not allowed.")
    return tuple(normalized)


@dataclass(frozen=True, eq=False)
class TableRef:
    """The schema-qualified identity of a SQL Server table."""

    schema: str
    table: str

    def __post_init__(self) -> None:
        _validated_identifier(self.schema, "schema")
        _validated_identifier(self.table, "table")

    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.table}"

    @property
    def identity_key(self) -> tuple[str, str]:
        return (_identifier_key(self.schema), _identifier_key(self.table))

    def __hash__(self) -> int:
        return hash(self.identity_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TableRef):
            return NotImplemented
        return self.identity_key == other.identity_key


@dataclass(frozen=True)
class MandatoryFilterPolicy:
    """A typed predicate that must be injected for each matching table scope."""

    table: TableRef
    column: str
    operator: FilterOperator | str
    value: object

    def __post_init__(self) -> None:
        if not isinstance(self.table, TableRef):
            raise QuerySpaceValidationError(
                "mandatory filter table must be a TableRef."
            )
        _validated_identifier(self.column, "mandatory filter column")
        if not isinstance(self.operator, FilterOperator):
            try:
                object.__setattr__(self, "operator", FilterOperator(self.operator))
            except ValueError as error:
                raise QuerySpaceValidationError(
                    "mandatory filter operator is not supported."
                ) from error
        if self.operator is FilterOperator.IN:
            if not isinstance(self.value, (list, tuple, set, frozenset)):
                raise QuerySpaceValidationError(
                    "IN mandatory filter value must be a collection."
                )
        else:
            if not (
                self.value is None or isinstance(self.value, (bool, int, float, str))
            ):
                raise QuerySpaceValidationError(
                    "mandatory filter value must be a scalar or None."
                )

    @property
    def identity_key(self) -> tuple[tuple[str, str], str, str]:
        assert isinstance(self.operator, FilterOperator)
        return (
            self.table.identity_key,
            self.column.casefold(),
            self.operator.value,
        )


@dataclass(frozen=True)
class ColumnSpec:
    """Lightweight developer declaration for one physical column."""

    name: str
    data_type: str | None = None
    nullable: bool | None = None
    primary_key: bool = False
    description: str | None = None
    alias: str | None = None
    allowed: bool = True
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    synonyms: Collection[str] = field(default_factory=tuple)
    semantic_type: SemanticType | str | None = None
    unit: str | None = None
    example_values: Collection[str] = field(default_factory=tuple)
    capabilities: ColumnCapabilities | None = None
    interpretation_warnings: Collection[str] = field(default_factory=tuple)
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    access: ColumnAccessLevel | ColumnAccess | str | None = None
    profiles: Mapping[str, ColumnAccess] | None = None

    def __post_init__(self) -> None:
        _validated_identifier(self.name, "column name")
        if self.data_type is not None:
            _validated_identifier(self.data_type, "column data type")
        if self.nullable is not None and not isinstance(self.nullable, bool):
            raise QuerySpaceValidationError("column nullable must be a bool or None.")
        if not isinstance(self.primary_key, bool):
            raise QuerySpaceValidationError("column primary_key must be a bool.")
        if not isinstance(self.allowed, bool):
            raise QuerySpaceValidationError("column allowed must be a bool.")
        access = self.access
        if access is None:
            access = (
                ColumnAccessLevel.USER_ALLOWED
                if self.allowed
                else ColumnAccessLevel.DENIED
            )
        elif isinstance(access, ColumnAccess):
            if access.result_access == ResultAccess.HIDDEN and (
                access.capabilities is None or not access.capabilities.any_enabled
            ):
                access = ColumnAccessLevel.DENIED
            elif access.capabilities and not access.selectable and access.filterable:
                access = ColumnAccessLevel.POLICY_ONLY
            else:
                access = ColumnAccessLevel.USER_ALLOWED

        elif not isinstance(access, ColumnAccessLevel):
            try:
                access = ColumnAccessLevel(access)
            except ValueError as error:
                raise QuerySpaceValidationError(
                    "column access must be user_allowed, policy_only, or denied."
                ) from error
        if not self.allowed and access is not ColumnAccessLevel.DENIED:
            raise QuerySpaceValidationError(
                "allowed=False conflicts with a non-denied column access mode."
            )
        object.__setattr__(self, "access", access)
        if self.profiles is not None:
            norm_profiles: dict[str, ColumnAccess] = {}
            for p_name, p_access in self.profiles.items():
                p_key = AccessProfile(p_name).name
                if not isinstance(p_access, ColumnAccess):
                    raise QuerySpaceValidationError(
                        f"Profile {p_name!r} access must be a ColumnAccess."
                    )
                norm_profiles[p_key] = p_access
            object.__setattr__(self, "profiles", MappingProxyType(norm_profiles))
        _optional_identifier(self.alias, "column alias")
        object.__setattr__(
            self, "synonyms", _semantic_terms(self.synonyms, "column synonym", 12)
        )
        object.__setattr__(
            self,
            "example_values",
            _semantic_terms(self.example_values, "example value", 3),
        )
        object.__setattr__(
            self,
            "interpretation_warnings",
            _semantic_terms(
                self.interpretation_warnings,
                "interpretation warning",
                10,
                max_length=1000,
            ),
        )
        if self.semantic_type is not None and not isinstance(
            self.semantic_type, (SemanticType, str)
        ):
            raise SemanticValidationError(
                "semantic_type must be a SemanticType, string, or None."
            )
        if isinstance(self.semantic_type, str) and not self.semantic_type.strip():
            raise SemanticValidationError("semantic_type cannot be empty.")
        if self.unit is not None and not self.unit.strip():
            raise SemanticValidationError("unit cannot be empty.")
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
        for label, value in (
            ("length", self.length),
            ("precision", self.precision),
            ("scale", self.scale),
        ):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise QuerySpaceValidationError(
                    f"column {label} must be a non-negative int or None."
                )

    @property
    def identity_key(self) -> str:
        return _identifier_key(self.name)


@dataclass(frozen=True)
class TableSpec:
    """Developer declaration or resolved metadata for one physical table."""

    ref: TableRef
    columns: Collection[ColumnSpec] = field(default_factory=tuple)
    description: str | None = None
    alias: str | None = None
    synonyms: Collection[str] = field(default_factory=tuple)
    business_rules: Collection[BusinessRule | str] = field(default_factory=tuple)
    interpretation_warnings: Collection[str] = field(default_factory=tuple)
    profiles: Mapping[str, TableAccess] | None = None
    required_filters: Collection[RequiredFilter] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.ref, TableRef):
            raise QuerySpaceValidationError("table ref must be a TableRef.")
        object.__setattr__(self, "columns", tuple(self.columns))
        _optional_identifier(self.alias, "table alias")
        if self.profiles is not None:
            norm_t_profiles: dict[str, TableAccess] = {}
            for p_name, p_access in self.profiles.items():
                p_key = AccessProfile(p_name).name
                if not isinstance(p_access, TableAccess):
                    raise QuerySpaceValidationError(
                        f"Table profile {p_name!r} access must be a TableAccess."
                    )
                norm_t_profiles[p_key] = p_access
            object.__setattr__(self, "profiles", MappingProxyType(norm_t_profiles))
        norm_filters: list[RequiredFilter] = []
        for req_filter in self.required_filters:
            if not isinstance(req_filter, RequiredFilter):
                raise QuerySpaceValidationError(
                    "required_filters entries must be RequiredFilter instances."
                )
            if req_filter.table is None:
                req_filter = RequiredFilter(
                    table=self.ref,
                    column=req_filter.column,
                    operator=req_filter.operator,
                    value_from_context=req_filter.value_from_context,
                    value=req_filter.value,
                )
            norm_filters.append(req_filter)
        object.__setattr__(self, "required_filters", tuple(norm_filters))
        object.__setattr__(
            self, "synonyms", _semantic_terms(self.synonyms, "table synonym", 12)
        )
        object.__setattr__(
            self,
            "interpretation_warnings",
            _semantic_terms(
                self.interpretation_warnings,
                "interpretation warning",
                10,
                max_length=1000,
            ),
        )
        rules = tuple(
            rule
            if isinstance(rule, BusinessRule)
            else BusinessRule(str(rule), self.ref)
            for rule in self.business_rules
        )
        object.__setattr__(self, "business_rules", rules)
        physical: dict[str, ColumnSpec] = {}
        for column in self.columns:
            if not isinstance(column, ColumnSpec):
                raise QuerySpaceValidationError(
                    f"{self.ref.full_name} contains a non-ColumnSpec column."
                )
            if column.identity_key in physical:
                raise QuerySpaceValidationError(
                    f"Duplicate column {column.name!r} in {self.ref.full_name}."
                )
            physical[column.identity_key] = column
        aliases: dict[str, ColumnSpec] = {}
        for column in self.columns:
            if column.alias is None:
                continue
            key = _identifier_key(column.alias)
            owner = physical.get(key)
            if owner is not None and owner is not column:
                raise AliasConflictError(
                    f"Column alias {column.alias!r} in {self.ref.full_name} "
                    "conflicts with a physical column."
                )
            if key in aliases:
                raise AliasConflictError(
                    f"Duplicate column alias {column.alias!r} in {self.ref.full_name}."
                )
            aliases[key] = column

    def get_column(self, name: str, *, include_aliases: bool = False) -> ColumnSpec:
        key = _identifier_key(_validated_identifier(name, "column name"))
        for column in self.columns:
            if column.identity_key == key or (
                include_aliases
                and column.alias is not None
                and _identifier_key(column.alias) == key
            ):
                return column
        raise QuerySpaceLookupError(
            f"Column {name!r} is not present in {self.ref.full_name}."
        )


@dataclass(frozen=True)
class RelationshipSpec:
    """An allowed column relationship between two QuerySpace tables."""

    source_table: TableRef
    source_column: str
    target_table: TableRef
    target_column: str
    strict: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source_table, TableRef):
            raise QuerySpaceValidationError("source_table must be a TableRef.")
        if not isinstance(self.target_table, TableRef):
            raise QuerySpaceValidationError("target_table must be a TableRef.")
        _validated_identifier(self.source_column, "source column")
        _validated_identifier(self.target_column, "target column")
        if not isinstance(self.strict, bool):
            raise QuerySpaceValidationError("relationship strict must be a bool.")

    @property
    def identity_key(self) -> tuple[tuple[str, str], str, tuple[str, str], str]:
        return (
            self.source_table.identity_key,
            _identifier_key(self.source_column),
            self.target_table.identity_key,
            _identifier_key(self.target_column),
        )


@dataclass(frozen=True)
class ExecutionPolicy:
    """Execution limits enforced for SQL generated inside a QuerySpace."""

    max_rows: int = 100
    allow_execution: bool = True
    allow_select_star: bool = False
    allow_unlisted_joins: bool = False
    allow_unqualified_tables: bool = False
    max_joins: int = 5
    timeout_seconds: int = 15
    allow_subqueries: bool = True
    allow_ctes: bool = True
    allow_cross_join: bool = False
    allowed_join_types: Collection[JoinType | str] = field(
        default_factory=lambda: (JoinType.INNER, JoinType.LEFT)
    )
    mandatory_filters: Collection[MandatoryFilterPolicy | RequiredFilter] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_rows, int)
            or isinstance(self.max_rows, bool)
            or not 1 <= self.max_rows <= 1000
        ):
            raise QuerySpaceValidationError(
                "execution policy max_rows must be an int between 1 and 1000."
            )
        if not isinstance(self.allow_execution, bool):
            raise QuerySpaceValidationError(
                "execution policy allow_execution must be a bool."
            )
        if (
            not isinstance(self.max_joins, int)
            or isinstance(self.max_joins, bool)
            or self.max_joins < 0
        ):
            raise QuerySpaceValidationError(
                "execution policy max_joins must be a non-negative int."
            )
        if (
            not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
        ):
            raise QuerySpaceValidationError(
                "execution policy timeout_seconds must be a positive int."
            )
        for label, value in (
            ("allow_select_star", self.allow_select_star),
            ("allow_unlisted_joins", self.allow_unlisted_joins),
            ("allow_unqualified_tables", self.allow_unqualified_tables),
            ("allow_subqueries", self.allow_subqueries),
            ("allow_ctes", self.allow_ctes),
            ("allow_cross_join", self.allow_cross_join),
        ):
            if not isinstance(value, bool):
                raise QuerySpaceValidationError(
                    f"execution policy {label} must be a bool."
                )
        join_types: list[JoinType] = []
        for join_type in self.allowed_join_types:
            try:
                normalized = (
                    join_type
                    if isinstance(join_type, JoinType)
                    else JoinType(join_type)
                )
            except ValueError as error:
                raise QuerySpaceValidationError(
                    f"Unsupported join type {join_type!r}."
                ) from error
            if normalized not in join_types:
                join_types.append(normalized)
        object.__setattr__(self, "allowed_join_types", tuple(join_types))
        filters = tuple(self.mandatory_filters)
        if any(
            not isinstance(item, (MandatoryFilterPolicy, RequiredFilter))
            for item in filters
        ):
            raise QuerySpaceValidationError(
                "mandatory_filters must contain MandatoryFilterPolicy or RequiredFilter instances."
            )
        if len({getattr(item, "identity_key", id(item)) for item in filters}) != len(
            filters
        ):
            raise QuerySpaceValidationError("Duplicate mandatory filter policy.")
        object.__setattr__(self, "mandatory_filters", filters)


def _validate_space(
    tables: Collection[TableSpec],
    relationships: Collection[RelationshipSpec],
    execution_policy: ExecutionPolicy,
    *,
    require_resolved_columns: bool,
) -> None:
    if not tables:
        raise QuerySpaceValidationError("QuerySpace must contain at least one table.")
    if not isinstance(execution_policy, ExecutionPolicy):
        raise QuerySpaceValidationError("execution_policy must be an ExecutionPolicy.")
    tables_by_ref: dict[TableRef, TableSpec] = {}
    short_names: dict[str, list[TableSpec]] = {}
    aliases: dict[str, TableSpec] = {}
    for table in tables:
        if not isinstance(table, TableSpec):
            raise QuerySpaceValidationError(
                "QuerySpace tables must contain only TableSpec instances."
            )
        if table.ref in tables_by_ref:
            raise QuerySpaceValidationError(
                f"Duplicate table {table.ref.full_name!r} in QuerySpace."
            )
        tables_by_ref[table.ref] = table
        short_names.setdefault(_identifier_key(table.ref.table), []).append(table)
        if require_resolved_columns:
            if not table.columns:
                raise QuerySpaceValidationError(
                    f"Resolved table {table.ref.full_name} has no allowed columns."
                )
            for column in table.columns:
                if column.data_type is None or column.nullable is None:
                    raise QuerySpaceValidationError(
                        f"Resolved column {table.ref.full_name}.{column.name} "
                        "is missing physical metadata."
                    )
                if not column.allowed:
                    raise QuerySpaceValidationError(
                        "ResolvedQuerySpace cannot contain denied columns."
                    )
    for table in tables:
        if table.alias is None:
            continue
        key = _identifier_key(table.alias)
        physical_owners = short_names.get(key, [])
        if any(owner is not table for owner in physical_owners):
            raise AliasConflictError(
                f"Table alias {table.alias!r} conflicts with a physical table name."
            )
        if key in aliases:
            raise AliasConflictError(f"Duplicate table alias {table.alias!r}.")
        aliases[key] = table

    relationship_keys: set[tuple[tuple[str, str], str, tuple[str, str], str]] = set()
    for relationship in relationships:
        if not isinstance(relationship, RelationshipSpec):
            raise QuerySpaceValidationError(
                "QuerySpace relationships must contain only RelationshipSpec instances."
            )
        source = tables_by_ref.get(relationship.source_table)
        target = tables_by_ref.get(relationship.target_table)
        if source is None or target is None:
            raise QuerySpaceValidationError(
                "Relationship endpoints must both be inside QuerySpace."
            )
        if require_resolved_columns:
            try:
                source.get_column(relationship.source_column)
                target.get_column(relationship.target_column)
            except QuerySpaceLookupError as error:
                raise QuerySpaceValidationError(str(error)) from error
        if relationship.identity_key in relationship_keys:
            raise QuerySpaceValidationError("Duplicate relationship in QuerySpace.")
        relationship_keys.add(relationship.identity_key)
    for policy in execution_policy.mandatory_filters:
        if policy.table is None:
            continue
        policy_table = tables_by_ref.get(policy.table)
        if policy_table is None:
            raise QuerySpaceValidationError(
                f"Mandatory policy table {policy.table.full_name!r} is outside QuerySpace."
            )
        try:
            column = policy_table.get_column(policy.column)
        except QuerySpaceLookupError:
            if require_resolved_columns:
                raise QuerySpaceValidationError(
                    f"Mandatory policy column {policy.table.full_name}."
                    f"{policy.column} is unavailable."
                ) from None
            continue
        if column.access is ColumnAccess.DENIED:
            raise QuerySpaceValidationError(
                f"Mandatory policy column {policy.table.full_name}."
                f"{policy.column} is denied."
            )
        if (
            column.access is ColumnAccess.USER_ALLOWED
            and column.capabilities is not None
            and not column.capabilities.filterable
        ):
            raise QuerySpaceValidationError(
                f"Mandatory policy column {policy.table.full_name}."
                f"{policy.column} is not filterable."
            )


@dataclass(frozen=True)
class QuerySpace:
    """Immutable developer intent; catalog resolution is still required."""

    tables: Collection[TableSpec]
    relationships: Collection[RelationshipSpec] = field(default_factory=tuple)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    default_column_policy: DefaultColumnPolicy = DefaultColumnPolicy.DENY

    def __post_init__(self) -> None:
        object.__setattr__(self, "tables", tuple(self.tables))
        object.__setattr__(self, "relationships", tuple(self.relationships))
        if not isinstance(self.default_column_policy, DefaultColumnPolicy):
            try:
                object.__setattr__(
                    self,
                    "default_column_policy",
                    DefaultColumnPolicy(self.default_column_policy),
                )
            except ValueError as error:
                raise QuerySpaceValidationError(
                    "default_column_policy must be 'deny' or 'allow'."
                ) from error
        self.validate()

    @property
    def table_refs(self) -> frozenset[TableRef]:
        return frozenset(table.ref for table in self.tables)

    def validate(self) -> None:
        _validate_space(
            self.tables,
            self.relationships,
            self.execution_policy,
            require_resolved_columns=False,
        )

    def get_table(self, ref: TableRef) -> TableSpec:
        return _get_table(self.tables, ref)

    @classmethod
    def from_schema(
        cls,
        schema: str,
        *,
        engine: Engine,
        execution_policy: ExecutionPolicy | None = None,
    ) -> ResolvedQuerySpace:
        from querysmith.introspector import introspect_query_space

        return introspect_query_space(
            engine, schema=schema, execution_policy=execution_policy
        )

    @classmethod
    def from_table_refs(
        cls,
        table_refs: Iterable[TableRef],
        *,
        engine: Engine,
        execution_policy: ExecutionPolicy | None = None,
    ) -> ResolvedQuerySpace:
        from querysmith.introspector import introspect_query_space

        return introspect_query_space(
            engine,
            table_refs=tuple(table_refs),
            execution_policy=execution_policy,
        )

    @classmethod
    def from_legacy_tables(
        cls,
        tables: Iterable[Table],
        *,
        execution_policy: ExecutionPolicy | None = None,
    ) -> ResolvedQuerySpace:
        legacy_tables = tuple(tables)
        table_specs = tuple(
            TableSpec(
                ref=TableRef(table.schema_name, table.name),
                columns=tuple(
                    ColumnSpec(
                        name=column.name,
                        data_type=column.data_type,
                        nullable=column.is_nullable,
                        primary_key=column.is_primary_key,
                        description=column.description,
                    )
                    for column in table.columns
                ),
                description=table.description,
            )
            for table in legacy_tables
        )
        selected_refs = {table.ref for table in table_specs}
        relationships: list[RelationshipSpec] = []
        for table in legacy_tables:
            source = TableRef(table.schema_name, table.name)
            for foreign_key in table.foreign_keys:
                target = _legacy_foreign_key_target(table, foreign_key)
                if target in selected_refs:
                    relationships.append(
                        RelationshipSpec(
                            source,
                            foreign_key.column,
                            target,
                            foreign_key.referenced_column,
                        )
                    )
        return ResolvedQuerySpace(
            tables=table_specs,
            relationships=relationships,
            execution_policy=execution_policy
            or ExecutionPolicy(allow_unlisted_joins=True),
            default_column_policy=DefaultColumnPolicy.ALLOW,
        )


@dataclass(frozen=True)
class ResolvedColumn:
    """Composition of immutable physical, semantic, and capability metadata."""

    physical: CatalogColumn
    semantic: SemanticColumnSpec
    capabilities: ColumnCapabilities = field(default_factory=ColumnCapabilities)
    access: ColumnAccessLevel | ColumnAccess = ColumnAccessLevel.USER_ALLOWED
    profiles: Mapping[str, ColumnAccess] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.physical.name.casefold() != self.semantic.column.casefold():
            raise QuerySpaceValidationError(
                "Resolved column physical and semantic identities do not match."
            )
        if not isinstance(self.capabilities, ColumnCapabilities):
            raise QuerySpaceValidationError(
                "Resolved column capabilities must be ColumnCapabilities."
            )
        if not isinstance(self.access, (ColumnAccessLevel, ColumnAccess)):
            raise QuerySpaceValidationError(
                "Resolved column access must be a ColumnAccess or ColumnAccessLevel."
            )

    @property
    def name(self) -> str:
        return self.physical.name

    @property
    def data_type(self) -> str:
        return self.physical.data_type

    @property
    def nullable(self) -> bool:
        return self.physical.nullable

    @property
    def primary_key(self) -> bool:
        return self.physical.primary_key

    @property
    def length(self) -> int | None:
        return self.physical.length

    @property
    def precision(self) -> int | None:
        return self.physical.precision

    @property
    def scale(self) -> int | None:
        return self.physical.scale

    @property
    def alias(self) -> str | None:
        return self.semantic.alias

    @property
    def description(self) -> str | None:
        return self.semantic.description

    @property
    def allowed(self) -> bool:
        return self.access is not ColumnAccess.DENIED

    @property
    def user_allowed(self) -> bool:
        return self.access is ColumnAccess.USER_ALLOWED

    @property
    def identity_key(self) -> str:
        return self.name.casefold()


@dataclass(frozen=True)
class ResolvedTable:
    """Physical table composed with semantic metadata and allowed columns."""

    physical: CatalogTable
    semantic: SemanticTableSpec
    columns: Collection[ResolvedColumn]
    denied_columns: Collection[str] = field(default_factory=tuple, repr=False)
    profiles: Mapping[str, TableAccess] = field(default_factory=dict)
    required_filters: tuple[RequiredFilter, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", tuple(self.columns))
        object.__setattr__(self, "denied_columns", tuple(self.denied_columns))
        if self.physical.ref != self.semantic.ref:
            raise QuerySpaceValidationError(
                "Resolved table physical and semantic identities do not match."
            )
        if not self.columns:
            raise QuerySpaceValidationError(
                f"Resolved table {self.ref.full_name} has no allowed columns."
            )
        physical_names = {column.identity_key for column in self.physical.columns}
        resolved_names: set[str] = set()
        for column in self.columns:
            if not isinstance(column, ResolvedColumn):
                raise QuerySpaceValidationError(
                    "Resolved table columns must be ResolvedColumn instances."
                )
            if column.semantic.table != self.ref:
                raise QuerySpaceValidationError(
                    "Resolved column belongs to a different table."
                )
            if column.identity_key not in physical_names:
                raise QuerySpaceValidationError(
                    "Resolved column is absent from its physical table."
                )
            if column.identity_key in resolved_names:
                raise QuerySpaceValidationError(
                    f"Duplicate resolved column {column.name!r}."
                )
            resolved_names.add(column.identity_key)
        if resolved_names.intersection(name.casefold() for name in self.denied_columns):
            raise QuerySpaceValidationError(
                "A resolved column cannot also be listed as denied."
            )

    @property
    def ref(self) -> TableRef:
        return self.physical.ref

    @property
    def alias(self) -> str | None:
        return self.semantic.entity_name

    @property
    def description(self) -> str | None:
        return self.semantic.description

    def get_column(self, name: str, *, include_aliases: bool = False) -> ResolvedColumn:
        key = _identifier_key(_validated_identifier(name, "column name"))
        for column in self.columns:
            if column.identity_key == key or (
                include_aliases
                and column.alias is not None
                and column.alias.casefold() == key
            ):
                return column
        raise QuerySpaceLookupError(
            f"Column {name!r} is not present in {self.ref.full_name}."
        )


@dataclass(frozen=True)
class ResolvedQuerySpace:
    """Catalog-verified, composition-based space for downstream components."""

    tables: Collection[ResolvedTable | TableSpec]
    relationships: Collection[RelationshipSpec] = field(default_factory=tuple)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    default_column_policy: DefaultColumnPolicy = DefaultColumnPolicy.DENY

    def __post_init__(self) -> None:
        resolved_tables = tuple(
            table if isinstance(table, ResolvedTable) else _legacy_resolved_table(table)
            for table in self.tables
        )
        object.__setattr__(self, "tables", resolved_tables)
        object.__setattr__(self, "relationships", tuple(self.relationships))
        self.validate()

    @property
    def table_refs(self) -> frozenset[TableRef]:
        return frozenset(table.ref for table in self.tables)

    def validate(self) -> None:
        if not self.tables:
            raise QuerySpaceValidationError(
                "QuerySpace must contain at least one table."
            )
        refs: set[TableRef] = set()
        for table in self.tables:
            if not isinstance(table, ResolvedTable):
                raise QuerySpaceValidationError(
                    "Resolved tables must be ResolvedTable instances."
                )
            if table.ref in refs:
                raise QuerySpaceValidationError(
                    f"Duplicate table {table.ref.full_name!r} in QuerySpace."
                )
            refs.add(table.ref)
        relation_keys: set[tuple[tuple[str, str], str, tuple[str, str], str]] = set()
        for relationship in self.relationships:
            if (
                relationship.source_table not in refs
                or relationship.target_table not in refs
            ):
                raise QuerySpaceValidationError(
                    "Relationship endpoints must both be inside QuerySpace."
                )
            self.get_table(relationship.source_table).get_column(
                relationship.source_column
            )
            self.get_table(relationship.target_table).get_column(
                relationship.target_column
            )
            if relationship.identity_key in relation_keys:
                raise QuerySpaceValidationError("Duplicate relationship in QuerySpace.")
            relation_keys.add(relationship.identity_key)
        for policy in self.execution_policy.mandatory_filters:
            if policy.table is None:
                continue
            try:
                column = self.get_table(policy.table).get_column(policy.column)
            except QuerySpaceLookupError as error:
                raise QuerySpaceValidationError(
                    f"Mandatory policy target {policy.table.full_name}."
                    f"{policy.column} is unavailable."
                ) from error
            if column.access is ColumnAccess.DENIED:
                raise QuerySpaceValidationError(
                    f"Mandatory policy column {policy.table.full_name}."
                    f"{policy.column} is denied."
                )
            if (
                column.access is ColumnAccess.USER_ALLOWED
                and not column.capabilities.filterable
            ):
                raise QuerySpaceValidationError(
                    f"Mandatory policy column {policy.table.full_name}."
                    f"{policy.column} is not filterable."
                )

    def get_table(self, ref: TableRef) -> ResolvedTable:
        for table in self.tables:
            if isinstance(table, ResolvedTable) and table.ref == ref:
                return table
        raise QuerySpaceLookupError(
            f"Table {ref.full_name!r} is not present in QuerySpace."
        )


def _legacy_resolved_table(table: TableSpec) -> ResolvedTable:
    physical_columns: list[CatalogColumn] = []
    semantic_columns: list[ResolvedColumn] = []
    denied_columns: list[str] = []
    for column in table.columns:
        if column.data_type is None or column.nullable is None:
            raise QuerySpaceValidationError(
                f"Legacy resolved column {table.ref.full_name}.{column.name} is incomplete."
            )
        if column.access is ColumnAccess.DENIED:
            denied_columns.append(column.name)
            continue
        physical = CatalogColumn(
            column.name,
            column.data_type,
            column.nullable,
            column.primary_key,
            column.length,
            column.precision,
            column.scale,
        )
        semantic = SemanticColumnSpec(
            table.ref,
            column.name,
            column.description,
            column.alias,
            column.synonyms,
            column.semantic_type,
            column.unit,
            column.example_values,
            column.capabilities,
            column.interpretation_warnings,
            column.sensitivity,
        )
        physical_columns.append(physical)
        capabilities = column.capabilities or ColumnCapabilities()
        if (
            column.sensitivity
            in {DataSensitivity.SENSITIVE, DataSensitivity.RESTRICTED}
            and column.example_values
        ):
            raise CapabilityConflictError(
                f"Sensitive column {table.ref.full_name}.{column.name} cannot "
                "expose example values."
            )
        if column.sensitivity is DataSensitivity.RESTRICTED:
            if column.capabilities is not None and capabilities.any_enabled:
                raise CapabilityConflictError(
                    f"Restricted column {table.ref.full_name}.{column.name} cannot "
                    "enable operation capabilities."
                )
            capabilities = ColumnCapabilities.denied()
        if (
            column.access is ColumnAccessLevel.POLICY_ONLY
            or column.access is ColumnAccess.POLICY_ONLY
        ):
            if column.capabilities is not None and capabilities.any_enabled:
                raise CapabilityConflictError(
                    f"Policy-only column {table.ref.full_name}.{column.name} cannot "
                    "enable user operation capabilities."
                )
            capabilities = ColumnCapabilities.denied()
        assert isinstance(column.access, (ColumnAccessLevel, ColumnAccess))

        semantic_columns.append(
            ResolvedColumn(physical, semantic, capabilities, column.access)
        )
    catalog_table = CatalogTable(table.ref, physical_columns)
    semantic_table = SemanticTableSpec(
        table.ref,
        table.alias,
        table.description,
        table.synonyms,
        tuple(rule for rule in table.business_rules if isinstance(rule, BusinessRule)),
        table.interpretation_warnings,
    )
    norm_filters: list[RequiredFilter] = []
    for req_f in table.required_filters:
        if req_f.table is None:
            norm_filters.append(
                RequiredFilter(
                    table.ref,
                    req_f.column,
                    req_f.operator,
                    req_f.value_from_context,
                    req_f.value,
                )
            )
        else:
            norm_filters.append(req_f)
    return ResolvedTable(
        catalog_table,
        semantic_table,
        semantic_columns,
        denied_columns,
        required_filters=tuple(norm_filters),
    )


def _get_table(tables: Collection[TableSpec], ref: TableRef) -> TableSpec:
    if not isinstance(ref, TableRef):
        raise QuerySpaceLookupError("QuerySpace lookup requires a TableRef.")
    for table in tables:
        if table.ref == ref:
            return table
    raise QuerySpaceLookupError(
        f"Table {ref.full_name!r} is not present in QuerySpace."
    )


@dataclass
class Column:
    """Original SQL Server column model retained for backward compatibility."""

    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    description: str | None = None


@dataclass
class ForeignKey:
    """Original SQL Server foreign-key model retained for compatibility."""

    column: str
    referenced_table: str
    referenced_column: str


@dataclass
class Table:
    """Original mutable table model retained for backward compatibility."""

    schema_name: str
    name: str
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    description: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.schema_name}.{self.name}"


def _legacy_foreign_key_target(table: Table, foreign_key: ForeignKey) -> TableRef:
    if "." in foreign_key.referenced_table:
        schema, name = foreign_key.referenced_table.split(".", maxsplit=1)
        return TableRef(schema, name)
    return TableRef(table.schema_name, foreign_key.referenced_table)


@dataclass(frozen=True)
class ProfiledQuerySpace:
    """Immutable resolved QuerySpace scoped exclusively to an active AccessProfile."""

    access_profile: AccessProfile
    resolved_query_space: ResolvedQuerySpace
    table_access: Mapping[TableRef, TableAccess] = field(default_factory=dict)
    column_access: Mapping[tuple[TableRef, str], ColumnAccess] = field(
        default_factory=dict
    )
    effective_capabilities: Mapping[tuple[TableRef, str], ColumnCapabilities] = field(
        default_factory=dict
    )
    result_access: Mapping[tuple[TableRef, str], ResultAccess] = field(
        default_factory=dict
    )
    masking_policies: Mapping[tuple[TableRef, str], MaskingPolicy] = field(
        default_factory=dict
    )
    required_filters: tuple[RequiredFilter, ...] = field(default_factory=tuple)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)

    def __post_init__(self) -> None:
        if not isinstance(self.access_profile, AccessProfile):
            raise QuerySpaceValidationError(
                "ProfiledQuerySpace requires an AccessProfile."
            )
        if not isinstance(self.resolved_query_space, ResolvedQuerySpace):
            raise QuerySpaceValidationError(
                "ProfiledQuerySpace requires a ResolvedQuerySpace."
            )

    @property
    def table_refs(self) -> tuple[TableRef, ...]:
        return tuple(
            ref for ref, access in self.table_access.items() if access.available
        )

    def is_table_available(self, ref: TableRef) -> bool:
        access = self.table_access.get(ref)
        return access is not None and access.available

    def get_column_access(self, ref: TableRef, column_name: str) -> ColumnAccess | None:
        return self.column_access.get((ref, column_name.casefold()))

    def get_effective_capabilities(
        self, ref: TableRef, column_name: str
    ) -> ColumnCapabilities:
        caps = self.effective_capabilities.get((ref, column_name.casefold()))
        return caps if caps is not None else ColumnCapabilities.denied()

    def get_result_access(self, ref: TableRef, column_name: str) -> ResultAccess:
        res = self.result_access.get((ref, column_name.casefold()))
        return res if res is not None else ResultAccess.HIDDEN

    def get_masking_policy(
        self, ref: TableRef, column_name: str
    ) -> MaskingPolicy | None:
        return self.masking_policies.get((ref, column_name.casefold()))
