"""Stateless composition of developer, physical, and semantic catalogs."""

from __future__ import annotations

from typing import Protocol

from querysmith.catalog import (
    CatalogColumn,
    CatalogSnapshot,
    CatalogTable,
    normalize_type,
    relationship_types_compatible,
    types_compatible,
)
from querysmith.models import (
    AliasConflictError,
    ColumnAccess,
    ColumnAccessLevel,
    ColumnNotFoundError,
    ColumnSpec,
    ColumnTypeMismatchError,
    DefaultColumnPolicy,
    ExecutionPolicy,
    FilterOperator,
    ForbiddenColumnError,
    QuerySpace,
    RelationshipResolutionError,
    RelationshipSpec,
    ResolvedColumn,
    ResolvedQuerySpace,
    ResolvedTable,
    TableNotFoundError,
    TableRef,
    TableSpec,
)
from querysmith.semantic import (
    BusinessRuleValidationError,
    CapabilityConflictError,
    ColumnCapabilities,
    DataSensitivity,
    SemanticCatalog,
    SemanticColumnSpec,
    SemanticTableSpec,
    SemanticType,
    SemanticTypeMismatchError,
    SynonymConflictError,
)


class CatalogIntrospector(Protocol):
    def inspect_tables(self, table_refs: tuple[TableRef, ...]) -> CatalogSnapshot:
        """Return physical metadata for exact requested identities."""


class CatalogResolver:
    """Resolve developer declarations into immutable composed metadata."""

    def __init__(self, introspector: CatalogIntrospector) -> None:
        self.introspector = introspector

    def resolve(
        self, query_space: QuerySpace | ResolvedQuerySpace
    ) -> ResolvedQuerySpace:
        if isinstance(query_space, ResolvedQuerySpace):
            query_space.validate()
            return query_space
        query_space.validate()
        requested_refs = tuple(table.ref for table in query_space.tables)
        snapshot = self.introspector.inspect_tables(requested_refs)
        catalog_by_ref = {table.ref: table for table in snapshot.tables}
        missing = [ref.full_name for ref in requested_refs if ref not in catalog_by_ref]
        if missing:
            raise TableNotFoundError(
                "Catalog did not find requested table(s): " + ", ".join(sorted(missing))
            )

        for developer in query_space.tables:
            _validate_catalog_aliases(developer, catalog_by_ref[developer.ref])
        semantic_catalog = SemanticCatalog.from_query_space(query_space)
        _validate_semantic_terms(semantic_catalog, catalog_by_ref)
        resolved_tables = tuple(
            _resolve_table(
                developer,
                catalog_by_ref[developer.ref],
                semantic_catalog,
                query_space.default_column_policy,
            )
            for developer in query_space.tables
        )
        resolved_by_ref = {table.ref: table for table in resolved_tables}
        _validate_mandatory_policies(query_space.execution_policy, resolved_by_ref)
        relationships = _resolve_relationships(
            query_space,
            snapshot,
            resolved_by_ref,
            catalog_by_ref,
        )
        _validate_business_rules(resolved_tables)
        return ResolvedQuerySpace(
            resolved_tables,
            relationships,
            query_space.execution_policy,
            query_space.default_column_policy,
        )


def _resolve_table(
    developer: TableSpec,
    catalog: CatalogTable,
    semantic_catalog: SemanticCatalog,
    policy: DefaultColumnPolicy,
) -> ResolvedTable:
    _validate_catalog_aliases(developer, catalog)
    declared = {column.identity_key: column for column in developer.columns}
    physical = {column.identity_key: column for column in catalog.columns}
    missing = [
        column.name
        for column in developer.columns
        if column.identity_key not in physical
    ]
    if missing:
        raise ColumnNotFoundError(
            f"Catalog did not find column(s) in {developer.ref.full_name}: "
            + ", ".join(missing)
        )
    resolved: list[ResolvedColumn] = []
    denied: list[str] = []
    for catalog_column in catalog.columns:
        declaration = declared.get(catalog_column.identity_key)
        if declaration is not None and declaration.access is ColumnAccess.DENIED:
            if (
                declaration.capabilities is not None
                and declaration.capabilities.any_enabled
            ):
                raise CapabilityConflictError(
                    f"Denied column {developer.ref.full_name}.{declaration.name} "
                    "cannot enable operation capabilities."
                )
            denied.append(catalog_column.name)
            continue
        include = declaration is not None or policy is DefaultColumnPolicy.ALLOW
        if not include:
            continue
        semantic = semantic_catalog.get_column(developer.ref, catalog_column.name)
        if semantic is None:
            semantic = SemanticColumnSpec(developer.ref, catalog_column.name)
        resolved.append(
            _resolve_column(developer.ref, declaration, catalog_column, semantic)
        )
    if not resolved:
        raise ForbiddenColumnError(
            f"Table {developer.ref.full_name} exposes no allowed columns."
        )
    semantic_table = semantic_catalog.get_table(developer.ref) or SemanticTableSpec(
        developer.ref
    )
    allowed_catalog = CatalogTable(
        catalog.ref, tuple(column.physical for column in resolved)
    )
    return ResolvedTable(
        allowed_catalog,
        semantic_table,
        resolved,
        denied,
        profiles=developer.profiles or {},
        required_filters=tuple(developer.required_filters),
    )


def _resolve_column(
    table_ref: TableRef,
    declaration: ColumnSpec | None,
    catalog: CatalogColumn,
    semantic: SemanticColumnSpec,
) -> ResolvedColumn:
    if declaration is not None and declaration.data_type is not None:
        declared_type = normalize_type(
            declaration.data_type,
            length=declaration.length,
            precision=declaration.precision,
            scale=declaration.scale,
        )
        physical_type = normalize_type(
            catalog.data_type,
            length=catalog.length,
            precision=catalog.precision,
            scale=catalog.scale,
        )
        if not types_compatible(declared_type, physical_type):
            raise ColumnTypeMismatchError(
                f"Declared type {declaration.data_type!r} for "
                f"{table_ref.full_name}.{declaration.name} is incompatible with "
                f"catalog type {catalog.data_type!r}."
            )
    if (
        declaration is not None
        and declaration.nullable is not None
        and declaration.nullable != catalog.nullable
    ):
        raise ColumnTypeMismatchError(
            f"Declared nullability for {table_ref.full_name}.{declaration.name} "
            "does not match the catalog."
        )
    _validate_semantic_type(table_ref, catalog, semantic)
    capabilities = semantic.capabilities or ColumnCapabilities()
    access = (
        declaration.access
        if declaration is not None
        else ColumnAccessLevel.USER_ALLOWED
    )
    assert isinstance(access, (ColumnAccessLevel, ColumnAccess))
    if semantic.sensitivity is DataSensitivity.RESTRICTED:
        if semantic.capabilities is not None and semantic.capabilities.any_enabled:
            raise CapabilityConflictError(
                f"Restricted column {table_ref.full_name}.{catalog.name} cannot "
                "enable operation capabilities."
            )
        capabilities = ColumnCapabilities.denied()
    if access is ColumnAccessLevel.POLICY_ONLY or access is ColumnAccess.POLICY_ONLY:
        if semantic.capabilities is not None and semantic.capabilities.any_enabled:
            raise CapabilityConflictError(
                f"Policy-only column {table_ref.full_name}.{catalog.name} cannot "
                "enable user operation capabilities."
            )
        capabilities = ColumnCapabilities.denied()

    if (
        semantic.sensitivity in {DataSensitivity.SENSITIVE, DataSensitivity.RESTRICTED}
        and semantic.example_values
    ):
        raise CapabilityConflictError(
            f"Sensitive column {table_ref.full_name}.{catalog.name} cannot expose example values."
        )
    col_profiles = (
        declaration.profiles if declaration is not None and declaration.profiles else {}
    )
    return ResolvedColumn(
        catalog, semantic, capabilities, access, profiles=col_profiles
    )


def _validate_mandatory_policies(
    policy: ExecutionPolicy,
    tables: dict[TableRef, ResolvedTable],
) -> None:
    numeric = {
        "tinyint",
        "smallint",
        "int",
        "bigint",
        "decimal",
        "numeric",
        "money",
        "smallmoney",
        "float",
        "real",
    }
    textual = {
        "char",
        "varchar",
        "nchar",
        "nvarchar",
        "text",
        "ntext",
        "uniqueidentifier",
    }
    temporal = {
        "date",
        "datetime",
        "datetime2",
        "smalldatetime",
        "datetimeoffset",
        "time",
    }
    for mandatory in policy.mandatory_filters:
        if mandatory.table is None:
            continue
        table = tables.get(mandatory.table)
        if table is None:
            raise BusinessRuleValidationError(
                f"Mandatory policy table {mandatory.table.full_name} is unavailable."
            )
        try:
            column = table.get_column(mandatory.column)
        except KeyError as error:
            raise BusinessRuleValidationError(
                f"Mandatory policy column {mandatory.table.full_name}."
                f"{mandatory.column} is unavailable."
            ) from error
        if (
            column.access is ColumnAccess.USER_ALLOWED
            and not column.capabilities.filterable
        ):
            raise CapabilityConflictError(
                f"Mandatory policy column {mandatory.table.full_name}."
                f"{mandatory.column} is not filterable."
            )
        value = mandatory.value
        if value is None:
            if mandatory.operator not in {FilterOperator.EQ, FilterOperator.NE}:
                raise BusinessRuleValidationError(
                    "Null mandatory policy values require equality or inequality."
                )
            continue
        base = normalize_type(column.data_type).base
        compatible = (
            (base == "bit" and isinstance(value, bool))
            or (
                base in numeric
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
            or (base in textual and isinstance(value, str))
            or (base in temporal and isinstance(value, str))
        )
        if not compatible:
            raise BusinessRuleValidationError(
                f"Mandatory policy value type is incompatible with "
                f"{mandatory.table.full_name}.{column.name}."
            )


def _resolve_relationships(
    query_space: QuerySpace,
    snapshot: CatalogSnapshot,
    resolved_tables: dict[TableRef, ResolvedTable],
    catalog_tables: dict[TableRef, CatalogTable],
) -> tuple[RelationshipSpec, ...]:
    relationships: list[RelationshipSpec] = []
    keys: set[tuple[tuple[str, str], str, tuple[str, str], str]] = set()
    for relationship in query_space.relationships:
        resolved = _resolve_manual_relationship(
            relationship, resolved_tables, catalog_tables
        )
        relationships.append(resolved)
        keys.add(resolved.identity_key)
    for relationship in snapshot.relationships:
        if relationship.identity_key in keys:
            continue
        source = resolved_tables.get(relationship.source_table)
        target = resolved_tables.get(relationship.target_table)
        if source is None or target is None:
            continue
        try:
            source_column = source.get_column(relationship.source_column)
            target_column = target.get_column(relationship.target_column)
        except KeyError:
            continue
        source_physical = catalog_tables[relationship.source_table].get_column(
            relationship.source_column
        )
        target_physical = catalog_tables[relationship.target_table].get_column(
            relationship.target_column
        )
        if (
            source_physical is None
            or target_physical is None
            or not relationship_types_compatible(source_physical, target_physical)
            or not source_column.capabilities.joinable
            or not target_column.capabilities.joinable
        ):
            continue
        relationships.append(relationship)
        keys.add(relationship.identity_key)
    return tuple(relationships)


def _resolve_manual_relationship(
    relationship: RelationshipSpec,
    resolved_tables: dict[TableRef, ResolvedTable],
    catalog_tables: dict[TableRef, CatalogTable],
) -> RelationshipSpec:
    source = resolved_tables.get(relationship.source_table)
    target = resolved_tables.get(relationship.target_table)
    if source is None or target is None:
        raise RelationshipResolutionError(
            "Manual relationship endpoints must both be inside QuerySpace."
        )
    source_physical = catalog_tables[relationship.source_table].get_column(
        relationship.source_column
    )
    target_physical = catalog_tables[relationship.target_table].get_column(
        relationship.target_column
    )
    if source_physical is None or target_physical is None:
        raise RelationshipResolutionError(
            "Manual relationship references a column missing from the catalog."
        )
    try:
        source_column = source.get_column(relationship.source_column)
        target_column = target.get_column(relationship.target_column)
    except KeyError as error:
        raise ForbiddenColumnError(
            "Manual relationship references a denied column."
        ) from error
    if (
        not source_column.capabilities.joinable
        or not target_column.capabilities.joinable
    ):
        raise CapabilityConflictError(
            "Manual relationship requires JOIN capability on both endpoints."
        )
    if not relationship_types_compatible(source_physical, target_physical):
        raise RelationshipResolutionError(
            "Manual relationship columns have incompatible physical types."
        )
    return RelationshipSpec(
        source.ref,
        source_column.name,
        target.ref,
        target_column.name,
        relationship.strict,
    )


def _validate_catalog_aliases(developer: TableSpec, catalog: CatalogTable) -> None:
    physical = {column.identity_key: column for column in catalog.columns}
    for declaration in developer.columns:
        if declaration.alias is None:
            continue
        owner = physical.get(declaration.alias.casefold())
        if owner is not None and owner.identity_key != declaration.identity_key:
            raise AliasConflictError(
                f"Column alias {declaration.alias!r} in {developer.ref.full_name} "
                f"conflicts with physical column {owner.name!r}."
            )


def _validate_semantic_terms(
    semantic: SemanticCatalog,
    physical: dict[TableRef, CatalogTable],
) -> None:
    table_terms: dict[str, TableRef] = {
        table.ref.table.casefold(): table.ref for table in physical.values()
    }
    for semantic_table in semantic.tables:
        if semantic_table.ref not in physical:
            raise TableNotFoundError(
                f"Semantic table {semantic_table.ref.full_name} is outside QuerySpace."
            )
        terms = (
            (semantic_table.entity_name,) if semantic_table.entity_name else ()
        ) + tuple(semantic_table.synonyms)
        if len({term.casefold() for term in terms}) != len(terms):
            raise SynonymConflictError(
                f"Semantic table terms for {semantic_table.ref.full_name} overlap."
            )
        for term in terms:
            key = term.casefold()
            owner = table_terms.get(key)
            if owner is not None and owner != semantic_table.ref:
                raise SynonymConflictError(
                    f"Semantic table term {term!r} is ambiguous between "
                    f"{owner.full_name} and {semantic_table.ref.full_name}."
                )
            table_terms[key] = semantic_table.ref
    columns_by_table: dict[TableRef, dict[str, str]] = {}
    for catalog_table in physical.values():
        columns_by_table[catalog_table.ref] = {
            column.name.casefold(): column.name for column in catalog_table.columns
        }
    for column in semantic.columns:
        requested_catalog = physical.get(column.table)
        if (
            requested_catalog is None
            or requested_catalog.get_column(column.column) is None
        ):
            raise ColumnNotFoundError(
                f"Semantic column {column.table.full_name}.{column.column} does not exist."
            )
        owners = columns_by_table[column.table]
        terms = ((column.alias,) if column.alias else ()) + tuple(column.synonyms)
        if len({term.casefold() for term in terms}) != len(terms):
            raise SynonymConflictError(
                f"Semantic column terms for {column.table.full_name}."
                f"{column.column} overlap."
            )
        for term in terms:
            key = term.casefold()
            physical_owner = owners.get(key)
            if (
                physical_owner is not None
                and physical_owner.casefold() != column.column.casefold()
            ):
                raise SynonymConflictError(
                    f"Semantic column term {term!r} in {column.table.full_name} "
                    f"conflicts with column {physical_owner!r}."
                )
            owners[key] = column.column


def _validate_semantic_type(
    table_ref: TableRef,
    physical: CatalogColumn,
    semantic: SemanticColumnSpec,
) -> None:
    semantic_type = semantic.semantic_type
    if semantic_type is None:
        if semantic.unit is not None:
            raise SemanticTypeMismatchError(
                "Unit requires a quantitative semantic type on "
                f"{table_ref.full_name}.{physical.name}."
            )
        return
    if not isinstance(semantic_type, SemanticType):
        return
    base = normalize_type(physical.data_type).base
    numeric = {
        "tinyint",
        "smallint",
        "int",
        "bigint",
        "decimal",
        "money",
        "smallmoney",
        "float",
        "real",
    }
    textual = {"char", "varchar", "nchar", "nvarchar", "text", "ntext"}
    temporal = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset"}
    compatible = {
        SemanticType.CURRENCY: base in numeric,
        SemanticType.QUANTITY: base in numeric,
        SemanticType.PERCENTAGE: base in numeric,
        SemanticType.DURATION: base in numeric,
        SemanticType.DATE: base in temporal,
        SemanticType.DATETIME: base in temporal,
        SemanticType.BOOLEAN: base == "bit",
        SemanticType.TEXT: base in textual,
        SemanticType.CATEGORY: base in textual,
        SemanticType.EMAIL: base in textual,
        SemanticType.PHONE: base in textual,
        SemanticType.URL: base in textual,
        SemanticType.ADDRESS: base in textual,
        SemanticType.PERSON_NAME: base in textual,
        SemanticType.IDENTIFIER: True,
        SemanticType.SENSITIVE_IDENTIFIER: True,
    }[semantic_type]
    if not compatible:
        raise SemanticTypeMismatchError(
            f"Semantic type {semantic_type.value!r} is incompatible with SQL type "
            f"{physical.data_type!r} for {table_ref.full_name}.{physical.name}."
        )
    if semantic.unit is not None and semantic_type not in {
        SemanticType.CURRENCY,
        SemanticType.QUANTITY,
        SemanticType.PERCENTAGE,
        SemanticType.DURATION,
    }:
        raise SemanticTypeMismatchError(
            f"Unit is not valid for semantic type {semantic_type.value!r} on "
            f"{table_ref.full_name}.{physical.name}."
        )


def _validate_business_rules(tables: tuple[ResolvedTable, ...]) -> None:
    by_ref = {table.ref: table for table in tables}
    for table in tables:
        for rule in table.semantic.business_rules:
            if rule.applies_to is not None and rule.applies_to not in by_ref:
                raise BusinessRuleValidationError(
                    f"Business rule on {table.ref.full_name} references table "
                    f"{rule.applies_to.full_name} outside QuerySpace."
                )
            target = by_ref.get(rule.applies_to or table.ref)
            assert target is not None
            for column in rule.applies_to_columns:
                try:
                    target.get_column(column)
                except KeyError as error:
                    raise BusinessRuleValidationError(
                        f"Business rule on {target.ref.full_name} references unavailable "
                        f"column {column!r}."
                    ) from error
