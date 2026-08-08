"""Unit tests for selective catalog resolution policies and validation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.models import (
    AliasConflictError,
    ColumnAccess,
    ColumnNotFoundError,
    ColumnSpec,
    ColumnTypeMismatchError,
    DefaultColumnPolicy,
    ExecutionPolicy,
    ForbiddenColumnError,
    MandatoryFilterPolicy,
    QuerySpace,
    QuerySpaceValidationError,
    RelationshipResolutionError,
    RelationshipSpec,
    TableNotFoundError,
    TableRef,
    TableSpec,
)
from querysmith.resolver import CatalogResolver
from querysmith.semantic import BusinessRuleValidationError

CUSTOMER = TableRef("CRM", "Customer")
ORDERS = TableRef("Sales", "Orders")
OUTSIDE = TableRef("Audit", "Events")


def _column(
    name: str,
    data_type: str = "int",
    *,
    nullable: bool = False,
    primary_key: bool = False,
    length: int | None = None,
) -> CatalogColumn:
    return CatalogColumn(
        name,
        data_type,
        nullable,
        primary_key,
        length,
        10,
        0,
    )


def _snapshot() -> CatalogSnapshot:
    return CatalogSnapshot(
        requested_refs=(CUSTOMER, ORDERS),
        tables=(
            CatalogTable(
                CUSTOMER,
                (
                    _column("CustomerId", primary_key=True),
                    _column("DisplayName", "nvarchar", length=100),
                    _column("SecretToken", "nvarchar", length=200),
                ),
            ),
            CatalogTable(
                ORDERS,
                (
                    _column("OrderId", primary_key=True),
                    _column("CustomerId"),
                    _column("InternalNote", "nvarchar", nullable=True, length=500),
                ),
            ),
        ),
        relationships=(
            RelationshipSpec(ORDERS, "CustomerId", CUSTOMER, "CustomerId"),
            RelationshipSpec(ORDERS, "OrderId", OUTSIDE, "EventId"),
        ),
    )


def _policy_snapshot() -> CatalogSnapshot:
    return CatalogSnapshot(
        requested_refs=(CUSTOMER,),
        tables=(
            CatalogTable(
                CUSTOMER,
                (
                    _column("CustomerId", primary_key=True),
                    _column("IsDeleted", "bit"),
                ),
            ),
        ),
    )


class FakeIntrospector:
    def __init__(self, snapshot: CatalogSnapshot | None = None) -> None:
        self.snapshot = snapshot or _snapshot()
        self.calls = 0
        self.refs: tuple[TableRef, ...] = ()

    def inspect_tables(self, table_refs: tuple[TableRef, ...]) -> CatalogSnapshot:
        self.calls += 1
        self.refs = table_refs
        return self.snapshot


def test_deny_is_default_and_exposes_only_declared_allowed_columns() -> None:
    developer = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [ColumnSpec("CustomerId"), ColumnSpec("SecretToken", allowed=False)],
            ),
            TableSpec(ORDERS, [ColumnSpec("CustomerId")]),
        ]
    )

    resolved = CatalogResolver(FakeIntrospector()).resolve(developer)

    assert [column.name for column in resolved.get_table(CUSTOMER).columns] == [
        "CustomerId"
    ]
    assert [column.name for column in resolved.get_table(ORDERS).columns] == [
        "CustomerId"
    ]
    assert resolved.relationships == (
        RelationshipSpec(ORDERS, "CustomerId", CUSTOMER, "CustomerId"),
    )


def test_allow_exposes_catalog_columns_except_explicit_denials() -> None:
    developer = QuerySpace(
        [
            TableSpec(CUSTOMER, [ColumnSpec("SecretToken", allowed=False)]),
            TableSpec(ORDERS, [ColumnSpec("InternalNote", allowed=False)]),
        ],
        default_column_policy=DefaultColumnPolicy.ALLOW,
    )

    resolved = CatalogResolver(FakeIntrospector()).resolve(developer)

    assert {column.name for column in resolved.get_table(CUSTOMER).columns} == {
        "CustomerId",
        "DisplayName",
    }
    assert {column.name for column in resolved.get_table(ORDERS).columns} == {
        "OrderId",
        "CustomerId",
    }
    assert all("SecretToken" not in repr(item) for item in resolved.tables)


def test_resolver_fills_optional_metadata_and_preserves_semantics_without_mutation() -> (
    None
):
    declared = ColumnSpec(
        "DisplayName", alias="customer_name", description="Public name"
    )
    developer = QuerySpace([TableSpec(CUSTOMER, [declared], alias="customers")])

    resolved = CatalogResolver(FakeIntrospector()).resolve(developer)
    column = resolved.get_table(CUSTOMER).get_column("DisplayName")

    assert (column.data_type, column.length, column.nullable) == (
        "nvarchar",
        100,
        False,
    )
    assert (column.alias, column.description) == ("customer_name", "Public name")
    assert declared.data_type is None and declared.nullable is None
    with pytest.raises(FrozenInstanceError):
        developer.tables = ()  # type: ignore[misc]


def test_resolving_an_already_resolved_space_is_idempotent() -> None:
    introspector = FakeIntrospector()
    developer = QuerySpace([TableSpec(CUSTOMER, [ColumnSpec("CustomerId")])])
    resolver = CatalogResolver(introspector)
    resolved = resolver.resolve(developer)

    assert resolver.resolve(resolved) is resolved
    assert introspector.calls == 1


@pytest.mark.parametrize(
    ("declaration", "error"),
    [
        (ColumnSpec("Missing"), ColumnNotFoundError),
        (ColumnSpec("CustomerId", "nvarchar"), ColumnTypeMismatchError),
        (ColumnSpec("CustomerId", nullable=True), ColumnTypeMismatchError),
        (ColumnSpec("DisplayName", "nvarchar(50)"), ColumnTypeMismatchError),
    ],
)
def test_declared_columns_must_match_catalog(
    declaration: ColumnSpec, error: type[Exception]
) -> None:
    developer = QuerySpace([TableSpec(CUSTOMER, [declaration])])

    with pytest.raises(error):
        CatalogResolver(FakeIntrospector()).resolve(developer)


def test_missing_table_has_typed_error() -> None:
    developer = QuerySpace(
        [TableSpec(TableRef("Missing", "Table"), [ColumnSpec("Id")])]
    )

    with pytest.raises(TableNotFoundError):
        CatalogResolver(FakeIntrospector()).resolve(developer)


def test_manual_non_fk_relationship_is_preserved_when_allowed_and_compatible() -> None:
    developer = QuerySpace(
        [
            TableSpec(CUSTOMER, [ColumnSpec("CustomerId")]),
            TableSpec(ORDERS, [ColumnSpec("OrderId")]),
        ],
        [RelationshipSpec(ORDERS, "OrderId", CUSTOMER, "CustomerId")],
    )

    resolved = CatalogResolver(FakeIntrospector()).resolve(developer)

    assert resolved.relationships == (
        RelationshipSpec(ORDERS, "OrderId", CUSTOMER, "CustomerId"),
    )


def test_manual_relationship_to_denied_column_fails_closed() -> None:
    developer = QuerySpace(
        [
            TableSpec(CUSTOMER, [ColumnSpec("CustomerId")]),
            TableSpec(
                ORDERS, [ColumnSpec("CustomerId", allowed=False), ColumnSpec("OrderId")]
            ),
        ],
        [RelationshipSpec(ORDERS, "CustomerId", CUSTOMER, "CustomerId")],
    )

    with pytest.raises(ForbiddenColumnError):
        CatalogResolver(FakeIntrospector()).resolve(developer)


def test_manual_relationship_requires_compatible_types() -> None:
    developer = QuerySpace(
        [
            TableSpec(CUSTOMER, [ColumnSpec("DisplayName")]),
            TableSpec(ORDERS, [ColumnSpec("OrderId")]),
        ],
        [RelationshipSpec(ORDERS, "OrderId", CUSTOMER, "DisplayName")],
    )

    with pytest.raises(RelationshipResolutionError):
        CatalogResolver(FakeIntrospector()).resolve(developer)


def test_aliases_are_case_insensitive_and_cannot_collide() -> None:
    with pytest.raises(AliasConflictError):
        TableSpec(
            CUSTOMER,
            [ColumnSpec("CustomerId"), ColumnSpec("DisplayName", alias="customerID")],
        )
    with pytest.raises(AliasConflictError):
        QuerySpace(
            [
                TableSpec(CUSTOMER, [ColumnSpec("CustomerId")], alias="orders"),
                TableSpec(ORDERS, [ColumnSpec("OrderId")]),
            ]
        )


def test_column_alias_cannot_collide_with_undeclared_catalog_column() -> None:
    developer = QuerySpace(
        [TableSpec(CUSTOMER, [ColumnSpec("CustomerId", alias="secretTOKEN")])]
    )

    with pytest.raises(AliasConflictError):
        CatalogResolver(FakeIntrospector()).resolve(developer)


def test_resolver_preserves_valid_policy_only_mandatory_target() -> None:
    developer = QuerySpace(
        [
            TableSpec(
                CUSTOMER,
                [
                    ColumnSpec("CustomerId"),
                    ColumnSpec("IsDeleted", access=ColumnAccess.POLICY_ONLY),
                ],
            )
        ],
        execution_policy=ExecutionPolicy(
            mandatory_filters=(
                MandatoryFilterPolicy(CUSTOMER, "IsDeleted", "=", False),
            )
        ),
    )

    resolved = CatalogResolver(FakeIntrospector(_policy_snapshot())).resolve(developer)

    policy_column = resolved.get_table(CUSTOMER).get_column("IsDeleted")
    assert policy_column.access is ColumnAccess.POLICY_ONLY
    assert policy_column.capabilities.filterable is False


def test_resolver_rejects_missing_or_type_incompatible_policy_target() -> None:
    missing = QuerySpace(
        [TableSpec(CUSTOMER)],
        execution_policy=ExecutionPolicy(
            mandatory_filters=(MandatoryFilterPolicy(CUSTOMER, "Missing", "=", False),)
        ),
        default_column_policy=DefaultColumnPolicy.ALLOW,
    )
    with pytest.raises(BusinessRuleValidationError, match="unavailable"):
        CatalogResolver(FakeIntrospector(_policy_snapshot())).resolve(missing)

    mismatched = QuerySpace(
        [TableSpec(CUSTOMER, [ColumnSpec("IsDeleted")])],
        execution_policy=ExecutionPolicy(
            mandatory_filters=(
                MandatoryFilterPolicy(CUSTOMER, "IsDeleted", "=", "false"),
            )
        ),
    )
    with pytest.raises(BusinessRuleValidationError, match="type is incompatible"):
        CatalogResolver(FakeIntrospector(_policy_snapshot())).resolve(mismatched)


def test_mandatory_policy_rejects_denied_column_and_unknown_operator() -> None:
    with pytest.raises(QuerySpaceValidationError, match="denied"):
        QuerySpace(
            [TableSpec(CUSTOMER, [ColumnSpec("IsDeleted", allowed=False)])],
            execution_policy=ExecutionPolicy(
                mandatory_filters=(
                    MandatoryFilterPolicy(CUSTOMER, "IsDeleted", "=", False),
                )
            ),
        )

    with pytest.raises(QuerySpaceValidationError, match="operator"):
        MandatoryFilterPolicy(CUSTOMER, "IsDeleted", "LIKE", False)
