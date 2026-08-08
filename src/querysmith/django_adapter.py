"""Django ORM Model Adapter for QuerySmith.

Provides automatic conversion of Django ORM Model classes into QuerySmith
QuerySpace declarations, physical catalog snapshots, and catalog introspectors.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.models import (
    ColumnAccess,
    ColumnCapabilities,
    ColumnSpec,
    ExecutionPolicy,
    MaskingPolicy,
    QuerySpace,
    RelationshipSpec,
    ResultAccess,
    TableAccess,
    TableRef,
    TableSpec,
)
from querysmith.semantic import SemanticType

# Common sensitive field names to automatically protect with profile security policies
SENSITIVE_FIELD_NAMES = {
    "national_code",
    "mobile_number",
    "mobilenumber",
    "phonenumber",
    "phone_number",
    "birth_date",
    "birthdate",
    "address",
    "postal_code",
    "postalcode",
    "otp_code",
    "otp_key",
}


def parse_db_table(table_str: str, default_schema: str = "Cor") -> TableRef:
    """Parse a Django db_table string into a schema-qualified TableRef.

    Handles table formats like:
      - 'Cor].[Provinces'
      - '[Cor].[Provinces]'
      - 'Cor.Provinces'
      - 'Cor].[Villages '
      - 'Form'
    """
    clean = table_str.strip()
    if clean.startswith("[") and clean.endswith("]"):
        clean = clean[1:-1]

    if "].[" in clean:
        parts = clean.split("].[")
    elif "].[" in table_str:
        parts = table_str.split("].[")
    elif "." in clean:
        parts = clean.split(".")
    else:
        parts = [default_schema, clean]

    schema = parts[0].strip().strip("[]")
    table_name = parts[1].strip().strip("[]")
    return TableRef(schema, table_name)


def get_field_column_name(field: Any) -> str:
    """Get physical database column name for a Django field."""
    if hasattr(field, "db_column") and field.db_column:
        return field.db_column
    if hasattr(field, "is_relation") and field.is_relation and (
        getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False)
    ):
        return f"{field.name}_id"
    return getattr(field, "name", "id")


def map_django_field_to_sql_type(field: Any) -> str:
    """Map Django field class to SQL database type string."""
    if hasattr(field, "is_relation") and field.is_relation and (
        getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False)
    ):
        target_field = getattr(field, "target_field", None)
        if target_field is not None and target_field is not field:
            return map_django_field_to_sql_type(target_field)

    internal_type = (
        field.get_internal_type()
        if hasattr(field, "get_internal_type")
        else field.__class__.__name__
    )

    if internal_type in (
        "IntegerField",
        "AutoField",
        "SmallAutoField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
    ):
        return "int"
    if internal_type in ("BigIntegerField", "BigAutoField"):
        return "bigint"
    if internal_type in ("CharField", "SlugField", "EmailField", "EncryptedField"):
        return "nvarchar"
    if internal_type == "TextField":
        return "nvarchar"
    if internal_type == "BooleanField":
        return "bit"
    if internal_type in ("DateTimeField", "DateField"):
        return "datetime"
    if internal_type in ("FloatField", "DecimalField"):
        return "decimal"
    if internal_type in ("BinaryField",):
        return "varbinary"
    if internal_type in ("JSONField",):
        return "nvarchar"
    return "nvarchar"


def django_models_to_query_space(
    models: Sequence[type[Any]],
    *,
    additional_relationships: Sequence[RelationshipSpec] | None = None,
    execution_policy: ExecutionPolicy | None = None,
) -> QuerySpace:
    """Convert a sequence of Django model classes into a QuerySmith QuerySpace."""
    tables: list[TableSpec] = []
    relationships: list[RelationshipSpec] = []
    if additional_relationships:
        relationships.extend(additional_relationships)
    processed_refs: set[TableRef] = set()

    all_table_refs = {
        parse_db_table(m._meta.db_table) for m in models if hasattr(m, "_meta")
    }
    seen_relationships: set[tuple[TableRef, str, TableRef, str]] = set()

    for model in models:
        if not hasattr(model, "_meta"):
            continue
        ref = parse_db_table(model._meta.db_table)
        if ref in processed_refs:
            continue
        processed_refs.add(ref)

        column_specs: list[ColumnSpec] = []

        pk = model._meta.pk
        pk_col_name = get_field_column_name(pk) if pk else "id"

        fields = [f for f in model._meta.get_fields() if not getattr(f, "auto_created", False) or getattr(f, "concrete", True)]

        seen_cols: set[str] = set()

        for field in fields:
            if getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False):
                continue

            col_name = get_field_column_name(field)
            if col_name in seen_cols:
                continue
            seen_cols.add(col_name)

            is_encrypted = (
                field.__class__.__name__ == "EncryptedField"
                or getattr(field, "is_national_code", False)
            )
            is_sensitive = (
                is_encrypted
                or col_name.lower() in SENSITIVE_FIELD_NAMES
                or field.name.lower() in SENSITIVE_FIELD_NAMES
            )

            profiles: dict[str, ColumnAccess] | None = None
            semantic_type: SemanticType | None = None

            internal_type = (
                field.get_internal_type()
                if hasattr(field, "get_internal_type")
                else field.__class__.__name__
            )

            if col_name == pk_col_name or getattr(field, "primary_key", False):
                semantic_type = SemanticType.IDENTIFIER
            elif internal_type == "BooleanField":
                semantic_type = SemanticType.BOOLEAN
            elif internal_type in ("DateTimeField", "DateField"):
                semantic_type = SemanticType.DATETIME
            elif internal_type in ("CharField", "TextField", "EncryptedField", "SlugField"):
                semantic_type = SemanticType.TEXT
            elif internal_type in ("IntegerField", "BigIntegerField", "PositiveIntegerField", "PositiveSmallIntegerField", "FloatField", "DecimalField"):
                semantic_type = SemanticType.QUANTITY

            if is_sensitive:
                profiles = {
                    "public": ColumnAccess.deny(),
                    "analyst": ColumnAccess(
                        selectable=False,
                        filterable=False,
                        sortable=False,
                        groupable=False,
                        aggregatable=False,
                        joinable=False,
                        result_access=ResultAccess.HIDDEN,
                    ),
                    "internal": ColumnAccess(
                        selectable=True,
                        filterable=False,
                        result_access=ResultAccess.MASKED,
                        masking=MaskingPolicy.partial(visible_prefix=0, visible_suffix=4),
                    ),
                }

            column_specs.append(
                ColumnSpec(
                    name=col_name,
                    semantic_type=semantic_type,
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                        aggregatable=True,
                        joinable=True,
                    ),
                    profiles=profiles,
                )
            )

            # Extract relationship specs for foreign keys / one-to-one
            if (
                getattr(field, "is_relation", False)
                and (getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False))
                and getattr(field, "related_model", None)
            ):
                target_model = field.related_model
                if hasattr(target_model, "_meta"):
                    target_ref = parse_db_table(target_model._meta.db_table)
                    target_pk = target_model._meta.pk
                    target_pk_col = (
                        get_field_column_name(target_pk) if target_pk else "id"
                    )

                    rel_key = (target_ref, target_pk_col, ref, col_name)
                    if target_ref in all_table_refs and rel_key not in seen_relationships:
                        seen_relationships.add(rel_key)
                        relationships.append(
                            RelationshipSpec(
                                source_table=target_ref,
                                source_column=target_pk_col,
                                target_table=ref,
                                target_column=col_name,
                            )
                        )

        doc = model.__doc__
        desc = f"Table for model {model.__name__}"
        if doc and isinstance(doc, str):
            first_line = " ".join(doc.strip().splitlines()[0].split())
            if first_line and len(first_line) <= 100:
                desc = first_line

        tables.append(
            TableSpec(
                ref=ref,
                description=desc,
                columns=column_specs,
                profiles={
                    "public": TableAccess(available=True),
                    "analyst": TableAccess(available=True),
                    "internal": TableAccess(available=True),
                },
            )
        )

    if execution_policy is None:
        execution_policy = ExecutionPolicy(
            allow_select_star=False,
            max_joins=5,
            max_rows=100,
            timeout_seconds=30,
            allow_subqueries=True,
            allow_ctes=True,
            allow_cross_join=False,
        )

    return QuerySpace(
        tables=tables,
        relationships=relationships,
        execution_policy=execution_policy,
    )


class DjangoCatalogIntrospector:
    """Introspector to deliver physical metadata snapshots from Django Model classes."""

    def __init__(self, models: Sequence[type[Any]]) -> None:
        self.models = models
        self.catalog_by_ref: dict[TableRef, CatalogTable] = {}

        for model in models:
            if not hasattr(model, "_meta"):
                continue
            ref = parse_db_table(model._meta.db_table)
            columns: list[CatalogColumn] = []

            seen_cols: set[str] = set()
            pk = model._meta.pk
            pk_col_name = get_field_column_name(pk) if pk else "id"

            fields = [f for f in model._meta.get_fields() if not getattr(f, "auto_created", False) or getattr(f, "concrete", True)]
            for field in fields:
                if getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False):
                    continue
                col_name = get_field_column_name(field)
                if col_name in seen_cols:
                    continue
                seen_cols.add(col_name)

                sql_type = map_django_field_to_sql_type(field)
                is_pk = col_name == pk_col_name or getattr(field, "primary_key", False)
                nullable = getattr(field, "null", True)

                columns.append(
                    CatalogColumn(
                        name=col_name,
                        data_type=sql_type,
                        nullable=nullable,
                        primary_key=is_pk,
                    )
                )

            self.catalog_by_ref[ref] = CatalogTable(ref=ref, columns=tuple(columns))

    def inspect_tables(self, table_refs: Sequence[TableRef]) -> CatalogSnapshot:
        found_tables: list[CatalogTable] = []
        for ref in table_refs:
            if ref in self.catalog_by_ref:
                found_tables.append(self.catalog_by_ref[ref])

        return CatalogSnapshot(
            requested_refs=tuple(table_refs),
            tables=tuple(found_tables),
        )
