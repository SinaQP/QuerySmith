"""Semantic catalog validation and physical/semantic composition tests."""

from __future__ import annotations

import pytest

from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.models import (
    ColumnSpec,
    QuerySpace,
    RelationshipSpec,
    TableRef,
    TableSpec,
)
from querysmith.resolver import CatalogResolver
from querysmith.semantic import (
    BusinessRule,
    BusinessRuleValidationError,
    CapabilityConflictError,
    ColumnCapabilities,
    DataSensitivity,
    SemanticType,
    SemanticTypeMismatchError,
    SemanticValidationError,
    SynonymConflictError,
)

CUSTOMER = TableRef("Sales", "Customer")
ORDER = TableRef("Sales", "Order")


class FakeIntrospector:
    def inspect_tables(self, table_refs: tuple[TableRef, ...]) -> CatalogSnapshot:
        return CatalogSnapshot(
            requested_refs=table_refs,
            tables=(
                CatalogTable(
                    CUSTOMER,
                    (
                        CatalogColumn("CustomerId", "int", False, True),
                        CatalogColumn("DisplayName", "nvarchar", False, length=100),
                        CatalogColumn("Secret", "nvarchar", False, length=100),
                    ),
                ),
                CatalogTable(
                    ORDER,
                    (
                        CatalogColumn("OrderId", "int", False, True),
                        CatalogColumn("CustomerId", "int", False),
                        CatalogColumn("Total", "decimal", False, precision=12, scale=2),
                        CatalogColumn("CreatedAt", "datetime2", False),
                    ),
                ),
            ),
            relationships=(
                RelationshipSpec(ORDER, "CustomerId", CUSTOMER, "CustomerId"),
            ),
        )


def _resolve(space: QuerySpace):
    return CatalogResolver(FakeIntrospector()).resolve(space)


def test_resolver_composes_physical_semantic_and_capability_metadata() -> None:
    declared = ColumnSpec(
        "Total",
        alias="order_value",
        description="Final payable amount",
        synonyms=("مبلغ سفارش", "order total"),
        semantic_type=SemanticType.CURRENCY,
        unit="IRR",
        example_values=("125000",),
        capabilities=ColumnCapabilities(joinable=False),
        interpretation_warnings=("Includes tax",),
        sensitivity=DataSensitivity.INTERNAL,
    )
    space = QuerySpace(
        [
            TableSpec(
                ORDER,
                [declared],
                alias="orders",
                description="Commercial orders",
                synonyms=("سفارش‌ها",),
                business_rules=(
                    BusinessRule("Ignore cancelled orders", ORDER, ("Total",)),
                ),
            )
        ]
    )

    resolved = _resolve(space)
    table = resolved.get_table(ORDER)
    column = table.get_column("Total")

    assert table.physical.ref == ORDER
    assert table.semantic.entity_name == "orders"
    assert column.physical.data_type == "decimal"
    assert column.semantic.alias == "order_value"
    assert column.capabilities.joinable is False
    assert declared.data_type is None
    assert declared.nullable is None


@pytest.mark.parametrize(
    ("column", "semantic_type"),
    [
        ("Total", SemanticType.EMAIL),
        ("CreatedAt", SemanticType.CURRENCY),
    ],
)
def test_semantic_type_must_match_physical_sql_type(
    column: str, semantic_type: SemanticType
) -> None:
    space = QuerySpace(
        [TableSpec(ORDER, [ColumnSpec(column, semantic_type=semantic_type)])]
    )

    with pytest.raises(SemanticTypeMismatchError):
        _resolve(space)


def test_unknown_semantic_type_is_rejected() -> None:
    space = QuerySpace(
        [TableSpec(ORDER, [ColumnSpec("Total", semantic_type="made_up")])]
    )

    with pytest.raises(SemanticValidationError, match="Unsupported semantic type"):
        _resolve(space)


def test_unit_requires_a_quantitative_semantic_type() -> None:
    space = QuerySpace([TableSpec(ORDER, [ColumnSpec("Total", unit="IRR")])])

    with pytest.raises(SemanticTypeMismatchError, match="Unit requires"):
        _resolve(space)


def test_denied_column_cannot_enable_capabilities() -> None:
    space = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [
                    ColumnSpec("CustomerId"),
                    ColumnSpec(
                        "Secret",
                        allowed=False,
                        capabilities=ColumnCapabilities(selectable=True),
                    ),
                ],
            )
        ]
    )

    with pytest.raises(CapabilityConflictError, match="Denied column"):
        _resolve(space)


def test_sensitive_columns_cannot_publish_example_values() -> None:
    space = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [
                    ColumnSpec(
                        "Secret",
                        example_values=("token-123",),
                        sensitivity=DataSensitivity.SENSITIVE,
                    )
                ],
            )
        ]
    )

    with pytest.raises(CapabilityConflictError, match="example values"):
        _resolve(space)


def test_restricted_column_defaults_to_no_operations() -> None:
    space = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [ColumnSpec("Secret", sensitivity=DataSensitivity.RESTRICTED)],
            )
        ]
    )

    column = _resolve(space).get_table(CUSTOMER).get_column("Secret")

    assert column.capabilities == ColumnCapabilities.denied()


def test_normalized_synonym_duplicates_and_collisions_are_rejected() -> None:
    with pytest.raises(SynonymConflictError):
        ColumnSpec("DisplayName", synonyms=("نام مشتری", "  نام   مشتری "))

    space = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [ColumnSpec("DisplayName", synonyms=("Secret",))],
            )
        ]
    )
    with pytest.raises(SynonymConflictError):
        _resolve(space)


def test_business_rule_references_must_resolve() -> None:
    space = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [ColumnSpec("CustomerId")],
                business_rules=(
                    BusinessRule("Use active customers", CUSTOMER, ("Missing",)),
                ),
            )
        ]
    )

    with pytest.raises(BusinessRuleValidationError, match="Missing"):
        _resolve(space)


def test_manual_relationship_requires_join_capability() -> None:
    space = QuerySpace(
        [
            TableSpec(CUSTOMER, [ColumnSpec("CustomerId")]),
            TableSpec(
                ORDER,
                [
                    ColumnSpec(
                        "CustomerId",
                        capabilities=ColumnCapabilities(joinable=False),
                    )
                ],
            ),
        ],
        [RelationshipSpec(ORDER, "CustomerId", CUSTOMER, "CustomerId")],
    )

    with pytest.raises(CapabilityConflictError, match="JOIN capability"):
        _resolve(space)


def test_example_count_and_length_are_bounded() -> None:
    with pytest.raises(SemanticValidationError):
        ColumnSpec("Total", example_values=("1", "2", "3", "4"))
    with pytest.raises(SemanticValidationError):
        ColumnSpec("Total", example_values=("x" * 121,))


def test_descriptions_use_text_length_limit_instead_of_term_limit() -> None:
    description = "x" * 121

    resolved = _resolve(
        QuerySpace(
            [
                TableSpec(
                    CUSTOMER,
                    [ColumnSpec("DisplayName", description=description)],
                    description=description,
                )
            ]
        )
    )

    assert resolved.get_table(CUSTOMER).description == description
    assert (
        resolved.get_table(CUSTOMER).get_column("DisplayName").description
        == description
    )

    with pytest.raises(SemanticValidationError, match="too long"):
        _resolve(
            QuerySpace(
                [
                    TableSpec(
                        CUSTOMER,
                        [ColumnSpec("CustomerId")],
                        description="x" * 1001,
                    )
                ]
            )
        )
