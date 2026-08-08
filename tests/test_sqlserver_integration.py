"""Real Microsoft SQL Server Integration Tests for QuerySmith.

Exercises multi-schema queries, tenant isolation, row limit truncation,
statement timeout (WAITFOR DELAY), profile enforcement, and execution boundary safety
against a live SQL Server instance (or skips gracefully if SQL Server is unreachable).
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

from querysmith.authorization import (
    SQLAuthorizationError,
    UnauthorizedColumnError,
    UnauthorizedTableError,
)
from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.exceptions import (
    QueryTimeoutError,
)
from querysmith.models import (
    ColumnAccess,
    ColumnAccessLevel,
    ColumnCapabilities,
    ColumnSpec,
    ExecutionPolicy,
    FilterOperator,
    MaskingPolicy,
    QuerySpace,
    RelationshipSpec,
    RequiredFilter,
    ResolvedQuerySpace,
    ResultAccess,
    TableAccess,
    TableRef,
    TableSpec,
)
from querysmith.pipeline import execute_select
from querysmith.resolver import CatalogResolver

# Mark all tests in this file with integration and sqlserver
pytestmark = [pytest.mark.integration, pytest.mark.sqlserver]


def get_integration_db_url() -> str:
    """Build SQL Server connection URL from environment variables."""
    host = os.getenv("MSSQL_HOST", "localhost")
    port = os.getenv("MSSQL_PORT", "14333")
    user = os.getenv("MSSQL_USER", "sa")
    password = os.getenv("MSSQL_SA_PASSWORD", "Password123!")
    database = os.getenv("MSSQL_DATABASE", "QuerySmithTestDB")
    driver = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    driver_fmt = driver.replace(" ", "+")
    return f"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver={driver_fmt}&TrustServerCertificate=yes"


class TrackingEngineWrapper:
    """Wraps a SQLAlchemy engine to count connect() calls for execution boundary assertions."""

    def __init__(self, target_engine: Engine) -> None:
        self.target_engine = target_engine
        self.connect_calls = 0

    def connect(self) -> Any:
        self.connect_calls += 1
        return self.target_engine.connect()

    def execution_options(self, **kwargs: Any) -> Any:
        return self.target_engine.execution_options(**kwargs)


@pytest.fixture(scope="module")
def sqlserver_engine() -> Generator[TrackingEngineWrapper, None, None]:
    """Create test database schema and seed multi-tenant data in SQL Server.

    Skips tests if SQL Server is not reachable.
    """
    db_url = get_integration_db_url()
    try:
        engine = create_engine(db_url, timeout=5)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"SQL Server connection failed ({exc}). Skipping integration tests."
        )

    # Setup database schemas and tables
    with engine.connect() as conn:
        conn.execute(
            text("""
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Person') EXEC('CREATE SCHEMA [Person]');
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Activity') EXEC('CREATE SCHEMA [Activity]');
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Sales') EXEC('CREATE SCHEMA [Sales]');
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Private') EXEC('CREATE SCHEMA [Private]');
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Tenant') EXEC('CREATE SCHEMA [Tenant]');

        IF OBJECT_ID('Person.Person', 'U') IS NOT NULL DROP TABLE Person.Person;
        IF OBJECT_ID('Activity.PersonActivity', 'U') IS NOT NULL DROP TABLE Activity.PersonActivity;
        IF OBJECT_ID('Sales.Orders', 'U') IS NOT NULL DROP TABLE Sales.Orders;
        IF OBJECT_ID('Private.Salary', 'U') IS NOT NULL DROP TABLE Private.Salary;
        IF OBJECT_ID('Tenant.TenantInfo', 'U') IS NOT NULL DROP TABLE Tenant.TenantInfo;

        CREATE TABLE Person.Person (
            BusinessEntityID INT PRIMARY KEY,
            FirstName NVARCHAR(50) NOT NULL,
            LastName NVARCHAR(50) NOT NULL,
            NationalIDNumber NVARCHAR(20) NOT NULL,
            TenantID INT NOT NULL
        );

        CREATE TABLE Activity.PersonActivity (
            ActivityID INT PRIMARY KEY,
            PersonID INT NOT NULL,
            ActivityType NVARCHAR(50) NOT NULL,
            TenantID INT NOT NULL
        );

        CREATE TABLE Sales.Orders (
            OrderID INT PRIMARY KEY,
            PersonID INT NOT NULL,
            TotalDue DECIMAL(18,2) NOT NULL,
            TenantID INT NOT NULL
        );

        CREATE TABLE Private.Salary (
            SalaryID INT PRIMARY KEY,
            PersonID INT NOT NULL,
            SalaryAmount DECIMAL(18,2) NOT NULL
        );

        CREATE TABLE Tenant.TenantInfo (
            TenantID INT PRIMARY KEY,
            TenantName NVARCHAR(100) NOT NULL
        );

        -- Seed Tenant data
        INSERT INTO Tenant.TenantInfo (TenantID, TenantName) VALUES (10, 'Tenant Alpha'), (20, 'Tenant Beta');

        -- Seed Person data for Tenant 10 & Tenant 20
        INSERT INTO Person.Person (BusinessEntityID, FirstName, LastName, NationalIDNumber, TenantID) VALUES
        (1, 'Alice', 'Smith', '111-222-3333', 10),
        (2, 'Bob', 'Jones', '444-555-6666', 10),
        (3, 'Charlie', 'Brown', '777-888-9999', 20);

        -- Seed Activity data
        INSERT INTO Activity.PersonActivity (ActivityID, PersonID, ActivityType, TenantID) VALUES
        (101, 1, 'Login', 10),
        (102, 1, 'Checkout', 10),
        (103, 2, 'Login', 10),
        (104, 3, 'Login', 20);

        -- Seed Orders data (15 rows for truncation testing)
        INSERT INTO Sales.Orders (OrderID, PersonID, TotalDue, TenantID) VALUES
        (1, 1, 100.00, 10), (2, 1, 150.00, 10), (3, 1, 200.00, 10),
        (4, 1, 250.00, 10), (5, 1, 300.00, 10), (6, 1, 350.00, 10),
        (7, 1, 400.00, 10), (8, 1, 450.00, 10), (9, 1, 500.00, 10),
        (10, 1, 550.00, 10), (11, 1, 600.00, 10), (12, 1, 650.00, 10),
        (13, 1, 700.00, 10), (14, 1, 750.00, 10), (15, 1, 800.00, 10);

        -- Seed Salary data
        INSERT INTO Private.Salary (SalaryID, PersonID, SalaryAmount) VALUES
        (1, 1, 95000.00),
        (2, 2, 85000.00),
        (3, 3, 75000.00);
        """)
        )
        conn.commit()

    wrapper = TrackingEngineWrapper(engine)
    yield wrapper

    # Cleanup after integration tests complete
    with engine.connect() as conn:
        conn.execute(
            text("""
        IF OBJECT_ID('Person.Person', 'U') IS NOT NULL DROP TABLE Person.Person;
        IF OBJECT_ID('Activity.PersonActivity', 'U') IS NOT NULL DROP TABLE Activity.PersonActivity;
        IF OBJECT_ID('Sales.Orders', 'U') IS NOT NULL DROP TABLE Sales.Orders;
        IF OBJECT_ID('Private.Salary', 'U') IS NOT NULL DROP TABLE Private.Salary;
        IF OBJECT_ID('Tenant.TenantInfo', 'U') IS NOT NULL DROP TABLE Tenant.TenantInfo;
        """)
        )
        conn.commit()


class FakeCatalogIntrospector:
    def __init__(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot

    def inspect_tables(self, refs: tuple[TableRef, ...]) -> CatalogSnapshot:
        return self.snapshot


@pytest.fixture
def integration_query_space() -> ResolvedQuerySpace:
    """ResolvedQuerySpace matching real SQL Server tables and schemas."""
    snapshot = CatalogSnapshot(
        requested_refs=(
            TableRef("Person", "Person"),
            TableRef("Activity", "PersonActivity"),
            TableRef("Sales", "Orders"),
            TableRef("Private", "Salary"),
        ),
        tables=(
            CatalogTable(
                ref=TableRef("Person", "Person"),
                columns=(
                    CatalogColumn(
                        "BusinessEntityID", "int", nullable=False, primary_key=True
                    ),
                    CatalogColumn("FirstName", "nvarchar", nullable=False),
                    CatalogColumn("LastName", "nvarchar", nullable=False),
                    CatalogColumn("NationalIDNumber", "nvarchar", nullable=False),
                    CatalogColumn("TenantID", "int", nullable=False),
                ),
            ),
            CatalogTable(
                ref=TableRef("Activity", "PersonActivity"),
                columns=(
                    CatalogColumn(
                        "ActivityID", "int", nullable=False, primary_key=True
                    ),
                    CatalogColumn("PersonID", "int", nullable=False),
                    CatalogColumn("ActivityType", "nvarchar", nullable=False),
                    CatalogColumn("TenantID", "int", nullable=False),
                ),
            ),
            CatalogTable(
                ref=TableRef("Sales", "Orders"),
                columns=(
                    CatalogColumn("OrderID", "int", nullable=False, primary_key=True),
                    CatalogColumn("PersonID", "int", nullable=False),
                    CatalogColumn("TotalDue", "decimal", nullable=False),
                    CatalogColumn("TenantID", "int", nullable=False),
                ),
            ),
            CatalogTable(
                ref=TableRef("Private", "Salary"),
                columns=(
                    CatalogColumn("SalaryID", "int", nullable=False, primary_key=True),
                    CatalogColumn("PersonID", "int", nullable=False),
                    CatalogColumn("SalaryAmount", "decimal", nullable=False),
                ),
            ),
        ),
    )

    qs = QuerySpace(
        tables=[
            TableSpec(
                ref=TableRef("Person", "Person"),
                columns=[
                    ColumnSpec("BusinessEntityID", capabilities=ColumnCapabilities()),
                    ColumnSpec("FirstName", capabilities=ColumnCapabilities()),
                    ColumnSpec("LastName", capabilities=ColumnCapabilities()),
                    ColumnSpec(
                        "NationalIDNumber",
                        capabilities=None,
                        access=ColumnAccessLevel.DENIED,
                        profiles={
                            "public": ColumnAccess.deny(),
                            "internal": ColumnAccess(
                                selectable=True,
                                filterable=True,
                                result_access=ResultAccess.MASKED,
                                masking=MaskingPolicy.partial(
                                    visible_prefix=0, visible_suffix=4
                                ),
                            ),
                        },
                    ),
                    ColumnSpec(
                        "TenantID",
                        capabilities=None,
                        access=ColumnAccessLevel.POLICY_ONLY,
                    ),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.EQ,
                        value_from_context="tenant_id",
                    )
                ],
                profiles={
                    "public": TableAccess(available=True),
                    "internal": TableAccess(available=True),
                },
            ),
            TableSpec(
                ref=TableRef("Activity", "PersonActivity"),
                columns=[
                    ColumnSpec("ActivityID", capabilities=ColumnCapabilities()),
                    ColumnSpec("PersonID", capabilities=ColumnCapabilities()),
                    ColumnSpec("ActivityType", capabilities=ColumnCapabilities()),
                    ColumnSpec(
                        "TenantID",
                        capabilities=None,
                        access=ColumnAccessLevel.POLICY_ONLY,
                    ),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.EQ,
                        value_from_context="tenant_id",
                    )
                ],
                profiles={
                    "public": TableAccess(available=True),
                    "internal": TableAccess(available=True),
                },
            ),
            TableSpec(
                ref=TableRef("Sales", "Orders"),
                columns=[
                    ColumnSpec("OrderID", capabilities=ColumnCapabilities()),
                    ColumnSpec("PersonID", capabilities=ColumnCapabilities()),
                    ColumnSpec("TotalDue", capabilities=ColumnCapabilities()),
                    ColumnSpec(
                        "TenantID",
                        capabilities=None,
                        access=ColumnAccessLevel.POLICY_ONLY,
                    ),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.EQ,
                        value_from_context="tenant_id",
                    )
                ],
                profiles={
                    "public": TableAccess(available=True),
                    "internal": TableAccess(available=True),
                },
            ),
            TableSpec(
                ref=TableRef("Private", "Salary"),
                columns=[
                    ColumnSpec("SalaryID", capabilities=ColumnCapabilities()),
                    ColumnSpec("PersonID", capabilities=ColumnCapabilities()),
                    ColumnSpec("SalaryAmount", capabilities=ColumnCapabilities()),
                ],
                profiles={
                    "public": TableAccess(available=False),
                    "internal": TableAccess(available=True),
                },
            ),
        ],
        relationships=[
            RelationshipSpec(
                TableRef("Person", "Person"),
                "BusinessEntityID",
                TableRef("Activity", "PersonActivity"),
                "PersonID",
            ),
            RelationshipSpec(
                TableRef("Person", "Person"),
                "BusinessEntityID",
                TableRef("Sales", "Orders"),
                "PersonID",
            ),
            RelationshipSpec(
                TableRef("Person", "Person"),
                "BusinessEntityID",
                TableRef("Private", "Salary"),
                "PersonID",
            ),
        ],
        execution_policy=ExecutionPolicy(
            allow_select_star=False, max_joins=3, max_rows=100
        ),
    )
    return CatalogResolver(FakeCatalogIntrospector(snapshot)).resolve(qs)


def test_integration_allowed_multi_schema_query(
    sqlserver_engine: TrackingEngineWrapper, integration_query_space: ResolvedQuerySpace
) -> None:
    """Execute valid multi-schema query on real SQL Server and verify results."""
    sql = """
    SELECT p.FirstName, a.ActivityType
    FROM [Person].[Person] AS p
    JOIN [Activity].[PersonActivity] AS a
        ON p.BusinessEntityID = a.PersonID
    """
    res = execute_select(
        sql,
        engine=sqlserver_engine,  # type: ignore
        query_space=integration_query_space,
        access_profile="public",
        runtime_context={"tenant_id": 10},
    )
    assert len(res.rows) > 0
    first_row = res.rows[0]
    assert "FirstName" in first_row
    assert "ActivityType" in first_row
    assert first_row["FirstName"] in ("Alice", "Bob")


def test_integration_forbidden_table_and_column_blocked(
    sqlserver_engine: TrackingEngineWrapper, integration_query_space: ResolvedQuerySpace
) -> None:
    """Verify denied queries (forbidden table or column) fail BEFORE reaching SQL Server."""
    sqlserver_engine.connect_calls = 0

    # 1. Denied Table (Private.Salary under public profile)
    sql_forbidden_table = "SELECT SalaryAmount FROM [Private].[Salary]"
    with pytest.raises((UnauthorizedTableError, SQLAuthorizationError)):
        execute_select(
            sql_forbidden_table,
            engine=sqlserver_engine,  # type: ignore
            query_space=integration_query_space,
            access_profile="public",
            runtime_context={"tenant_id": 10},
        )
    assert sqlserver_engine.connect_calls == 0

    # 2. Denied Column (NationalIDNumber under public profile)
    sql_forbidden_col = "SELECT NationalIDNumber FROM [Person].[Person]"
    with pytest.raises((UnauthorizedColumnError, SQLAuthorizationError)):
        execute_select(
            sql_forbidden_col,
            engine=sqlserver_engine,  # type: ignore
            query_space=integration_query_space,
            access_profile="public",
            runtime_context={"tenant_id": 10},
        )
    assert sqlserver_engine.connect_calls == 0


def test_integration_profile_enforcement(
    sqlserver_engine: TrackingEngineWrapper, integration_query_space: ResolvedQuerySpace
) -> None:
    """Verify internal profile allows salary queries while public profile blocks them before DB execution."""
    sqlserver_engine.connect_calls = 0
    sql = "SELECT p.FirstName, s.SalaryAmount FROM [Person].[Person] p JOIN [Private].[Salary] s ON p.BusinessEntityID = s.PersonID"

    # Public profile must fail closed before DB call
    with pytest.raises(SQLAuthorizationError):
        execute_select(
            sql,
            engine=sqlserver_engine,  # type: ignore
            query_space=integration_query_space,
            access_profile="public",
            runtime_context={"tenant_id": 10},
        )
    assert sqlserver_engine.connect_calls == 0

    # Internal profile must succeed on real SQL Server
    res = execute_select(
        sql,
        engine=sqlserver_engine,  # type: ignore
        query_space=integration_query_space,
        access_profile="internal",
        runtime_context={"tenant_id": 10},
    )
    assert len(res.rows) > 0
    assert "SalaryAmount" in res.rows[0]


def test_integration_tenant_isolation(
    sqlserver_engine: TrackingEngineWrapper, integration_query_space: ResolvedQuerySpace
) -> None:
    """Verify tenant_id context parameter is injected into SQL Server query parameters, isolating row access."""
    sql = "SELECT FirstName FROM [Person].[Person]"

    # Tenant 10 should return Alice & Bob
    res_10 = execute_select(
        sql,
        engine=sqlserver_engine,  # type: ignore
        query_space=integration_query_space,
        access_profile="public",
        runtime_context={"tenant_id": 10},
    )
    names_10 = {r["FirstName"] for r in res_10.rows}
    assert names_10 == {"Alice", "Bob"}

    # Tenant 20 should return Charlie only
    res_20 = execute_select(
        sql,
        engine=sqlserver_engine,  # type: ignore
        query_space=integration_query_space,
        access_profile="public",
        runtime_context={"tenant_id": 20},
    )
    names_20 = {r["FirstName"] for r in res_20.rows}
    assert names_20 == {"Charlie"}


def test_integration_waitfor_delay_timeout(
    sqlserver_engine: TrackingEngineWrapper, integration_query_space: ResolvedQuerySpace
) -> None:
    """Verify query execution timing out via WAITFOR DELAY on SQL Server raises QueryTimeoutError."""
    # Create query space with 1-second timeout policy
    timeout_space = ResolvedQuerySpace(
        tables=integration_query_space.tables,
        relationships=integration_query_space.relationships,
        execution_policy=ExecutionPolicy(allow_select_star=False, timeout_seconds=1),
    )
    sql = "SELECT FirstName FROM [Person].[Person]; WAITFOR DELAY '00:00:03';"

    with pytest.raises(QueryTimeoutError):
        execute_select(
            sql,
            engine=sqlserver_engine,  # type: ignore
            query_space=timeout_space,
            access_profile="public",
            runtime_context={"tenant_id": 10},
        )


def test_integration_max_rows_truncation(
    sqlserver_engine: TrackingEngineWrapper, integration_query_space: ResolvedQuerySpace
) -> None:
    """Verify max_rows policy truncates results and sets truncated=True on real SQL Server output."""
    sql = "SELECT OrderID, TotalDue FROM [Sales].[Orders]"
    res = execute_select(
        sql,
        engine=sqlserver_engine,  # type: ignore
        query_space=integration_query_space,
        access_profile="public",
        runtime_context={"tenant_id": 10},
        max_rows=5,
    )
    assert len(res.rows) == 5
    assert res.truncated is True
