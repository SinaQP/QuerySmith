# QuerySmith

QuerySmith is a Python 3.11+ package that turns Persian and English natural-language questions into Microsoft SQL Server T-SQL `SELECT` queries. It reads schema metadata, prompts an LLM with that context, validates the generated SQL, and can execute approved queries through SQL Server.

> **Early release:** QuerySmith is being prepared for its first public PyPI release.

## Features

- SQL Server schema introspection for tables, columns, primary keys, and foreign keys.
- Persian and English question support in the SQL-generation prompt.
- T-SQL query generation through an OpenAI-compatible client, with AvalAI defaults.
- Environment-based AvalAI and OpenAI-compatible configuration.
- A conservative guard that allows one `SELECT` or `WITH ... SELECT` query and rejects comments, multiple statements, DDL/DML, procedure access, `SELECT INTO`, external data access, and linked-server-style object names.
- Python helpers for configuration, connection creation, query generation, validation, and guarded execution.
- Programmer-defined `QuerySpace` scopes spanning selected tables from multiple schemas.
- **Access Profiles (Phase 5)**: Declarative profile-aware permissions (`AccessProfile`, `TableAccess`, `ColumnAccess`, `ResultAccess`, `MaskingPolicy`) for host application role-based and multi-tenant access control.
- **Result Policy & Execution Safety (Phase 6)**: AST result sanitization (`ResultSanitizer`, `SanitizedResult`), column-level masking (FULL, PARTIAL, CONSTANT), hidden column stripping, statement timeout enforcement, and shape constraints (`max_joins`, `allow_subqueries`, `allow_ctes`, `allow_cross_join`).


## Installation

### PyPI

After the first PyPI release, install QuerySmith with:

```bash
python -m pip install querysmith
```

### From source

```bash
git clone https://github.com/SinaQP/QuerySmith.git
cd QuerySmith
python -m venv .venv
```

Activate the environment:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install QuerySmith (and, for contributors, its configured development dependencies):

```bash
python -m pip install -e .
python -m pip install -e ".[dev]"
```

## Supported Python versions

QuerySmith requires Python 3.11 or newer.

## SQL Server prerequisites

QuerySmith requires access to a Microsoft SQL Server instance and credentials for the target database. Configure a server or host, optional port, database, username, password, and the installed ODBC driver name. Windows authentication is supported by setting `DB_TRUSTED_CONNECTION=true`.

> **ODBC driver required:** Installing `pyodbc` does not necessarily install the Microsoft SQL Server ODBC driver. `pyodbc` is the Python adapter; Microsoft ODBC Driver 18 for SQL Server is a separate system-level driver that may also be required. Driver installation differs across Windows, Linux, and macOS. Follow Microsoft's official ODBC-driver installation documentation for your platform, and make sure `DB_DRIVER` exactly matches an installed driver.

To view available driver names:

```python
import pyodbc

print(pyodbc.drivers())
```

`ODBC Driver 18 for SQL Server` is a common choice. QuerySmith's code defaults to version 17 when `DB_DRIVER` is not set, so set this variable explicitly when using version 18.

## Environment configuration

Create a local configuration file and keep it out of version control:

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

`.env` can contain database passwords and API keys; never commit it.

### SQL Server settings

| Variable | Required | Purpose |
| --- | --- | --- |
| `DB_SERVER` or `DB_HOST` | Yes | SQL Server host or server name. |
| `DB_PORT` | No | Port appended to a host as `host,port`; omit for a named instance. |
| `DB_DATABASE` or `DB_NAME` | Yes | Target database name. |
| `DB_USERNAME` or `DB_USER` | Yes* | SQL Server login name. |
| `DB_PASSWORD` | Yes* | SQL Server login password. |
| `DB_DRIVER` | No | Installed driver name, such as `ODBC Driver 18 for SQL Server`. |
| `DB_TRUSTED_CONNECTION` | No | Set to `true`, `1`, or `yes` to use Windows trusted authentication. |

\*These values are currently required by `load_config()` even when trusted authentication is enabled.

### LLM settings

`OpenAICompatibleClient` selects the first non-empty API key from `QUERYSMITH_LLM_API_KEY`, `AVALAI_API_KEY`, and `OPENAI_API_KEY`. Its base URL comes from `QUERYSMITH_LLM_BASE_URL` or `AVALAI_BASE_URL`, otherwise it defaults to `https://api.avalai.ir/v1`. `QUERYSMITH_LLM_MODEL` selects the model and defaults to `gpt-4o-mini`.

There is no `LLM_PROVIDER` setting: select a provider by supplying its API key and, where needed, its compatible base URL.

### AvalAI

AvalAI is used through its OpenAI-compatible API by default. A minimal configuration is:

```dotenv
AVALAI_API_KEY=your-avalai-api-key
AVALAI_BASE_URL=https://api.avalai.ir/v1
QUERYSMITH_LLM_MODEL=gpt-4o-mini
```

You can instead use the provider-neutral `QUERYSMITH_LLM_API_KEY` and `QUERYSMITH_LLM_BASE_URL` names.

### OpenAI

For the OpenAI API, configure its key and explicitly set the OpenAI-compatible endpoint:

```dotenv
OPENAI_API_KEY=your-openai-api-key
QUERYSMITH_LLM_BASE_URL=https://api.openai.com/v1
QUERYSMITH_LLM_MODEL=gpt-4o-mini
```

Do not place actual credentials in source files, documentation, or commits.

## Minimal working example

```python
from querysmith import load_config, make_engine
from querysmith.llm import OpenAICompatibleClient
from querysmith.pipeline import generate_query

config = load_config()
engine = make_engine(config)
client = OpenAICompatibleClient()

sql = generate_query(
    question="Show the top 10 customers by total order value.",
    engine=engine,
    client=client,
    schema="dbo",
)
print(sql)
```

The same flow accepts Persian questions, for example: `ده مشتری با بیشترین مبلغ سفارش را نمایش بده.`

For generation and execution in one authorized flow, use `ask(..., execute=True)`
with an active schema or `QuerySpace`. The lower-level `execute_select()` API
requires a `ResolvedQuerySpace` or `ProfiledQuerySpace`; raw SQL without an active
scope is rejected. Execution returns at most 100 rows by default (up to 1,000 when
requested and permitted by the active execution policy).

## Selective QuerySpace

QuerySmith separates programmer intent from trusted physical metadata:

1. A developer creates an immutable, possibly partial `QuerySpace`.
2. `SQLServerIntrospector.inspect_tables()` reads only its fully-qualified tables.
3. `CatalogResolver` merges catalog metadata and produces a `ResolvedQuerySpace`.
4. Only the resolved space reaches serialization, the LLM, the column-aware guard,
   or execution.

The schema-based facade remains available. It uses an explicit `allow` policy to
preserve the original all-column behavior and generates SQL without executing it:

```python
import querysmith

sql = querysmith.ask(
    question="List active customers",
    schema="Sales",
)
```

For tighter control, construct a selective scope from fully-qualified tables
across schemas. `data_type` and `nullable` are optional because resolution fills
them from SQL Server. The default column policy is `deny`, so undeclared catalog
columns are not exposed:

```python
from querysmith import (
    ColumnSpec,
    DefaultColumnPolicy,
    ExecutionPolicy,
    QuerySpace,
    RelationshipSpec,
    TableRef,
    TableSpec,
    ask,
    load_config,
    make_engine,
)

engine = make_engine(load_config())

person = TableSpec(
    ref=TableRef("Person", "Person"),
    alias="people",
    columns=[
        ColumnSpec("BusinessEntityID"),
        ColumnSpec("FirstName", alias="given_name"),
        ColumnSpec("PasswordHash", allowed=False),
    ],
)
employee = TableSpec(
    ref=TableRef("HumanResources", "Employee"),
    columns=[ColumnSpec("BusinessEntityID", data_type="int")],
)
employee_to_person = RelationshipSpec(
    source_table=employee.ref,
    source_column="BusinessEntityID",
    target_table=person.ref,
    target_column="BusinessEntityID",
)

query_space = QuerySpace(
    tables=[person, employee],
    relationships=[employee_to_person],
    execution_policy=ExecutionPolicy(max_rows=100),
    default_column_policy=DefaultColumnPolicy.DENY,
)

sql = ask(
    question="Show employees and their person records",
    query_space=query_space,
    engine=engine,
)
```

Use `DefaultColumnPolicy.ALLOW` to include every catalog column except declarations
with `allowed=False`. Aliases and descriptions are semantic prompt context only;
generated SQL must still use physical schema, table, and column identifiers.
Alias validation is case-insensitive and rejects duplicates or collisions with
physical names.

The typed introspection API can also be used directly:

```python
from querysmith import TableRef, inspect_tables

snapshot = inspect_tables(
    engine,
    [TableRef("Person", "Person"), TableRef("Sales", "Customer")],
)
```

This path uses three parameterized catalog queries for the exact table set rather
than reading every table in each schema. A single request is limited to 500 tables
to remain below SQL Server's parameter limit. `QuerySpace.from_schema()` remains
the full-schema compatibility adapter, while `QuerySpace.from_table_refs()` returns
an already resolved selective space.

Resolution fails before any LLM call or execution when a table or column is
missing, declared metadata is incompatible, an alias conflicts, a denied column
is used by a relationship, or a manual relationship is invalid. Catalog foreign
keys are added only when both endpoints and both allowed columns are in the
resolved space; valid manual relationships do not require a catalog foreign key.

The scoped guard validates columns used by projections, joins, filters, ordering,
grouping, and aggregates, including CTE and subquery lineage. Wildcards such as
`SELECT *`, `table.*`, and `COUNT(table.*)` are rejected for every resolved
QuerySpace; unqualified `COUNT(*)` remains available.

## Semantic QuerySpace

`QuerySpace` can describe business meaning without replacing trusted SQL Server
metadata. Physical names and types come from `CatalogSnapshot`; descriptions,
Persian or English synonyms, examples, units, semantic types, warnings, business
rules, sensitivity, and operation capabilities come from developer declarations.
`CatalogResolver` composes both into immutable `ResolvedTable` and
`ResolvedColumn` objects. It never mutates the developer input.

```python
from querysmith import (
    BusinessRule,
    ColumnCapabilities,
    ColumnSpec,
    DataSensitivity,
    QuerySpace,
    SemanticType,
    TableRef,
    TableSpec,
)

orders_ref = TableRef("Sales", "Orders")
orders = TableSpec(
    ref=orders_ref,
    alias="orders",
    description="Customer purchase orders",
    synonyms=("سفارش‌ها", "purchases"),
    columns=[
        ColumnSpec("OrderId", semantic_type=SemanticType.IDENTIFIER),
        ColumnSpec(
            "TotalDue",
            alias="order_value",
            synonyms=("مبلغ سفارش", "order total"),
            description="Final amount payable by the customer",
            semantic_type=SemanticType.CURRENCY,
            unit="IRR",
            example_values=("125000",),
            capabilities=ColumnCapabilities(joinable=False),
            sensitivity=DataSensitivity.INTERNAL,
            interpretation_warnings=("Includes tax",),
        ),
        ColumnSpec("InternalNote", allowed=False),
    ],
    business_rules=(
        BusinessRule(
            "Exclude cancelled orders unless the question asks for them",
            applies_to=orders_ref,
            applies_to_columns=("TotalDue",),
        ),
    ),
)

query_space = QuerySpace([orders])
```

The default for a custom `QuerySpace` remains deny-by-default: catalog columns
that are not declared are omitted. `allowed=False` denies every operation and
cannot be combined with enabled capabilities. `DataSensitivity.RESTRICTED` also
defaults to no capabilities, and sensitive or restricted columns cannot publish
example values.

Capabilities are enforced after generation as well as described to the model:

- `selectable` controls projections and non-aggregate expressions.
- `filterable` controls `WHERE` and `HAVING` references.
- `sortable` controls `ORDER BY`, including output aliases.
- `groupable` controls `GROUP BY`.
- `aggregatable` controls aggregate-function arguments.
- `joinable` controls join conditions and resolved relationships.

CTEs, subqueries, table aliases, and output aliases retain physical-column
lineage, so they cannot bypass a denied operation. Business rules are currently
advisory semantic guidance; QuerySmith validates their table and column
references but does not implement a rule DSL.

`ContextBuilder` creates the deterministic context sent to the LLM and clearly
labels physical identifiers separately from semantic hints. Existing
`serialize_query_space()` calls remain supported as a compatibility wrapper:

```python
from querysmith import ContextBuilder, ContextBuilderOptions

context = ContextBuilder(
    ContextBuilderOptions(include_examples=False)
).build(resolved_query_space)
```

## Row-Level Access Policy

QuerySmith enforces mandatory row-level security policies directly in the AST, completely independent of the LLM:

- **Application-Defined Policies**: Policies are declared in host application code via `RequiredFilter` on a `TableSpec` or `MandatoryFilterPolicy` on an `ExecutionPolicy`. The LLM cannot override, bypass, or remove these policies.
- **Trusted Runtime Context**: `runtime_context` is supplied strictly by host application code (e.g., authenticated session data like `tenant_id` or `user_id`). It is never parsed from prompt text or user questions, and prompt injection attempts cannot modify it.
- **Strict Parameterization**: All runtime values are injected using parameterized AST placeholders (e.g. `WHERE o.TenantID = :qs_policy_0_0` or `WHERE o.TenantID IN (:qs_policy_0_0_p0, :qs_policy_0_0_p1)`). Values are never formatted via string interpolation, eliminating SQL injection risks.
- **Policy-Only Columns**: Columns marked with `access=ColumnAccess.POLICY_ONLY` are excluded from the LLM prompt context and rejected if directly queried by the user/LLM. However, the policy injector can inject them as trusted physical predicates without exposing them in the final output projection.
- **CTE, Subquery & Outer Join Handling**:
  - **CTEs & Subqueries**: Policies are recursively injected into every physical table reference inside CTE definitions, subqueries, and set operation (`UNION`/`UNION ALL`) branches.
  - **Outer Joins**: Policies on the right (nullable) side of a `LEFT JOIN` are placed in the `ON` clause to preserve join semantics. For `RIGHT JOIN` and `FULL JOIN` where predicate placement cannot be safely proved, QuerySmith fails closed with `OuterJoinRewriteError`.
- **Injection vs Prompt Instructions**: Unlike prompt instructions which can be ignored or bypassed by LLMs, AST policy injection operates post-LLM on the parsed AST using fail-closed security guarantees.

### Usage Example

```python
from querysmith import (
    ColumnAccess,
    ColumnSpec,
    ExecutionPolicy,
    FilterOperator,
    QuerySpace,
    RequiredFilter,
    TableRef,
    TableSpec,
    ask,
    load_config,
    make_engine,
)

engine = make_engine(load_config())

sales_space = QuerySpace(
    tables=[
        TableSpec(
            ref=TableRef("Sales", "Orders"),
            columns=[
                ColumnSpec("OrderID"),
                ColumnSpec("TotalDue"),
                ColumnSpec("TenantID", access=ColumnAccess.POLICY_ONLY),
            ],
            required_filters=[
                RequiredFilter(
                    column="TenantID",
                    operator=FilterOperator.EQ,
                    value_from_context="tenant_id",
                ),
            ],
        ),
    ],
    execution_policy=ExecutionPolicy(max_rows=100),
)

# Mandatory tenant policy is automatically resolved from trusted runtime_context
sql = ask(
    question="Show my recent order totals",
    query_space=sales_space,
    runtime_context={"tenant_id": 42},
    engine=engine,
)
```

## SQL Authorization

QuerySmith treats generated SQL as untrusted input. It parses one T-SQL statement
with `sqlglot`, builds lexical scopes for aliases, CTEs, derived tables,
subqueries, correlations, and set operations, and authorizes physical identifiers
against the immutable `ResolvedQuerySpace`. Security decisions about tables,
columns, joins, functions, and query shape are made from AST nodes rather than
regular expressions.

Each physical column is checked independently for its operation. `selectable`,
`filterable`, `sortable`, `groupable`, `aggregatable`, and `joinable` therefore do
not imply one another. Unqualified ambiguous columns fail closed. Physical tables
must be schema-qualified unless `allow_unqualified_tables=True` explicitly permits
an unambiguous match; database- and server-qualified sources are rejected.

Projection wildcards are denied by default. `COUNT(*)` is safe because it does not
expose column values, while `SELECT *`, `table.*`, and `COUNT(table.*)` are rejected.
`allow_select_star=True` works only when every physical source column is
user-selectable and the resolved table has no denied columns.

`RelationshipSpec(strict=True)` is enforceable authorization metadata. Equality
joins must match a declared strict relationship in either direction, and all join
columns require `joinable=True`. Unlisted joins, complex cross-source predicates,
implicit comma joins, and disabled join types fail closed. A non-strict
relationship is semantic context only; it becomes usable only when the execution
policy explicitly sets `allow_unlisted_joins=True`.

Mandatory row predicates are typed `MandatoryFilterPolicy` values. A
`POLICY_ONLY` column is retained in trusted resolved metadata but omitted from LLM
context and rejected when generated SQL references it. The policy injector copies
the original AST, injects a parameterized predicate for every physical table
occurrence, places predicates for the nullable side of a `LEFT JOIN` in `ON`, and
adds or reduces the outer T-SQL `TOP` limit. Injection is deterministic and
idempotent. The rewritten SQL is parsed and fully authorized again before an
immutable `AuthorizedQuery` can cross the execution boundary.

```python
from querysmith import (
    CatalogResolver,
    ColumnAccess,
    ColumnSpec,
    ExecutionPolicy,
    MandatoryFilterPolicy,
    QuerySpace,
    SQLServerIntrospector,
    TableRef,
    TableSpec,
    authorize_query_in_space,
    execute_authorized_query,
    load_config,
    make_engine,
)
from querysmith.llm import OpenAICompatibleClient

engine = make_engine(load_config())
customer_ref = TableRef("Sales", "Customer")
developer_space = QuerySpace(
    tables=[
        TableSpec(
            customer_ref,
            columns=[
                ColumnSpec("CustomerId"),
                ColumnSpec("DisplayName"),
                ColumnSpec("IsDeleted", access=ColumnAccess.POLICY_ONLY),
                ColumnSpec("SecretToken", allowed=False),
            ],
        )
    ],
    execution_policy=ExecutionPolicy(
        max_rows=100,
        mandatory_filters=(
            MandatoryFilterPolicy(customer_ref, "IsDeleted", "=", False),
        ),
    ),
)
resolved_space = CatalogResolver(SQLServerIntrospector(engine)).resolve(
    developer_space
)
authorized = authorize_query_in_space(
    "List customers",
    resolved_space,
    OpenAICompatibleClient(),
)
rows = execute_authorized_query(engine, authorized, resolved_space)
```

Semantic `BusinessRule` text remains advisory prompt guidance. It is not an
enforceable policy unless represented by a typed execution policy such as
`MandatoryFilterPolicy`.

## Security Error Codes & Authorization Report

QuerySmith provides deterministic, machine-readable `AuthorizationReport` dataclasses and structured `AuthorizationErrorCode` enums for every authorization decision.

### Authorization Error Codes

| Error Code | Meaning |
| --- | --- |
| `TABLE_NOT_ALLOWED` | Physical table is not present in QuerySpace or disabled by access profile. |
| `COLUMN_SELECT_NOT_ALLOWED` | Column cannot be projected in `SELECT` clause. |
| `COLUMN_FILTER_NOT_ALLOWED` | Column cannot be used in `WHERE` / `HAVING` predicate filter. |
| `COLUMN_JOIN_NOT_ALLOWED` | Column cannot be used in `JOIN` condition. |
| `SELECT_STAR_NOT_ALLOWED` | `SELECT *` wildcard projection is forbidden by execution policy. |
| `AMBIGUOUS_COLUMN` | Column name cannot be resolved unambiguously to a single source table. |
| `RELATIONSHIP_NOT_ALLOWED` | Join condition does not match an explicit `RelationshipSpec`. |
| `ACCESS_PROFILE_NOT_ALLOWED` | Requested access profile is unknown or disabled. |
| `MANDATORY_FILTER_MISSING` | Required runtime context parameter is missing. |
| `MANDATORY_FILTER_CONFLICT` | User SQL predicate contradicts mandatory row-level policy. |
| `HIDDEN_COLUMN_EXPOSURE` | Output result exposes a hidden/denied column. |
| `MASKING_BYPASS_ATTEMPT` | Query attempts to bypass or transform a masked column. |

### Authorization Report Serialization

Every `AuthorizationReport` can be serialized cleanly:

```python
report = authorized.authorization
report_dict = report.to_dict()
report_json = report.model_dump_json(indent=2)
```

## Structured Audit Logging

QuerySmith provides zero-dependency structured audit logging for query lifecycle tracking, profile resolution, SQL generation, authorization checks, and execution results. Sensitive literal values and credentials are automatically redacted.

```python
from querysmith import PythonLoggingAuditLogger, AuditLoggingPolicy, ask

logger = PythonLoggingAuditLogger()

authorized = ask(
    "Show active orders",
    query_space=space,
    access_profile="analyst",
    runtime_context={"tenant_id": 10},
    audit_logger=logger,
)
```

### Audit Event Types

- `query_received`: Logged upon receiving a natural language question.
- `profile_resolved`: Logged when effective profile permissions are evaluated.
- `sql_generated`: Logged when LLM generates candidate SQL (literals redacted).
- `authorization_allowed` / `authorization_denied`: Logged upon AST authorization result.
- `execution_started` / `execution_succeeded` / `execution_failed`: Logged during database execution boundary.

## SQL Server Integration Testing

Run live integration tests against a Microsoft SQL Server container:

```bash
# Start SQL Server 2022 service container
docker-compose -f docker-compose.integration.yml up -d

# Execute integration tests
python -m pytest -v -m "integration"
```

## Security model

The AST authorization layer rejects comments, multiple statements, DDL/DML,
procedure access, `SELECT INTO`, external table functions, system metadata
discovery functions, unauthorized identifiers, capability violations, and invalid
relationships before execution. These checks are still one layer of defense. Use
a read-only SQL Server account restricted to the necessary schemas, tables, and
views, and add authentication, rate limiting, audit storage, and database resource
controls as appropriate for the deployment.

## Limitations

- Supports Microsoft SQL Server and T-SQL only.
- Generates and executes `SELECT` queries only.
- Requires access to an external OpenAI-compatible LLM service.
- SQL quality depends on the schema metadata, question clarity, and selected model.
- Complex or ambiguous questions can produce incorrect or inefficient queries.
- Database permissions and query-resource limits must be managed independently.

## Development and testing

```bash
python -m pip install -e ".[dev]"

# Unit tests
python -m pytest -q -m "not integration and not sqlserver"

# Full suite including adversarial security tests
python -m pytest -v tests/test_adversarial_security.py
```

## License

QuerySmith is released under the MIT License. See [LICENSE](LICENSE) for details.
