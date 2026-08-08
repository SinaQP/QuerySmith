# QuerySmith v0.2.0 — Marketing and Video Research Source of Truth

> Research date: 2026-08-07  
> Target candidate: local working tree reporting version `0.2.0`  
> Comparison baseline: Git tag `v0.1.0` at commit `c866e13`  
> Scope: repository implementation, tests, documentation, Git history, local build artifacts, and public package/release metadata  
> Purpose: factual input for later video creation. This document intentionally contains no finished video script, storyboard, caption, ad copy, voice-over, or campaign.

## 1. Executive source of truth

QuerySmith is an alpha-stage Python library/SDK for adding natural-language analytics to Microsoft SQL Server applications. It accepts Persian or English questions, gives an OpenAI-compatible LLM a deliberately scoped and semantically enriched description of the database, treats the returned SQL as untrusted, authorizes the SQL against developer policy, optionally injects mandatory row filters and a row limit into the SQL AST, re-authorizes the rewritten SQL, executes only the resulting `AuthorizedQuery`, and sanitizes the returned rows.

The most accurate conceptual description of v0.2.0 is:

> **A developer-controlled, policy-enforced Text-to-T-SQL SDK for Microsoft SQL Server.**

“Natural language to SQL” is true but incomplete. The meaningful v0.2.0 product is the control plane around generation: selective schema exposure, semantic context, per-operation column capabilities, access profiles, AST authorization, strict relationships, row-policy injection, execution limits, result masking, and audit events.

Release-state facts must be kept distinct:

- `pyproject.toml` and `querysmith.__version__` say `0.2.0`.
- Local `dist/` contains `querysmith-0.2.0-py3-none-any.whl` and `querysmith-0.2.0.tar.gz`.
- `CHANGELOG.md` labels all v0.2 work **Unreleased**.
- Git has only the `v0.1.0` tag; the repository `HEAD` is still that tag and the v0.2 implementation is in the working tree.
- PyPI currently publishes only `querysmith 0.1.0`; v0.2.0 is not publicly released there as of the research date.
- GitHub currently has no GitHub Release objects, even though it has the `v0.1.0` tag.

Therefore the safe public wording today is **“v0.2.0 candidate,” “upcoming v0.2.0,” or “local v0.2.0 build”**, not “v0.2.0 is available on PyPI.”

## 2. What QuerySmith is

### Product type

- A reusable Python library/SDK, not a hosted SaaS, standalone database server, BI product, or finished end-user application.
- It also includes `main.py`, an interactive developer playground/REPL demonstrating the library against a real database.
- It targets Python 3.11+ and Microsoft SQL Server/T-SQL.
- SQLAlchemy and `pyodbc` provide database connectivity.
- `sqlglot` parses and rewrites T-SQL as an AST.
- The default LLM adapter talks to OpenAI-compatible chat-completion APIs; its defaults target AvalAI, but an OpenAI-compatible endpoint can be configured.

### Problem it solves

A raw Text-to-SQL implementation usually sends a schema plus a question to a model and executes whatever comes back. That delegates both SQL generation and practical authorization to a probabilistic component. QuerySmith v0.2 separates those responsibilities:

- The developer declares which physical tables, columns, relationships, meanings, operations, profiles, and row policies exist for this use case.
- Physical metadata is verified against SQL Server before generation.
- The model receives only the effective scope for the active profile.
- Generated SQL is parsed and deterministically authorized after generation.
- Mandatory filters and limits are applied outside the model.
- Rewritten SQL is authorized again before execution.
- Returned rows are checked against projection metadata, hidden fields are omitted, and masked fields are redacted.

### Intended users

The natural users are Python backend developers, AI application engineers, SaaS/internal-tool teams, and developers building assistants or natural-language analytics on top of SQL Server. It is not currently aimed at users of PostgreSQL, MySQL, SQLite, arbitrary SQLAlchemy dialects, or no-code BI tools.

### Language support

Persian and English are explicitly supported at the **question/prompt** layer. There is no separate translation engine or language detector. The prompt tells the configured LLM to infer Persian and English intent, and developers can add Persian/English aliases and synonyms as semantic hints. SQL identifiers remain their real physical identifiers.

## 3. Actual v0.2.0 request flow

```text
Host application supplies:
  natural-language question + QuerySpace + active profile/runtime context
                              ↓
CatalogResolver verifies developer declarations against selected SQL Server tables
and produces an immutable ResolvedQuerySpace
                              ↓
AccessProfileResolver computes effective table/column/result permissions
                              ↓
Runtime context required by row policies is validated before the LLM call
                              ↓
ContextBuilder serializes only effective physical + semantic metadata
                              ↓
OpenAI-compatible LLM proposes one T-SQL read-only query
                              ↓
SQLParser parses the response as T-SQL; SQLAuthorizer checks query shape,
tables, columns by operation, wildcards, profiles, and relationships
                              ↓
PolicyInjector copies the AST, injects typed parameterized mandatory filters,
and adds/reduces the T-SQL TOP limit
                              ↓
The rewritten SQL is parsed and fully authorized again; physical table/column
sets are compared with the first authorization pass
                              ↓
Immutable AuthorizedQuery(sql + parameters + report + applied policies)
                     ↙ preview                 ↘ execute=True
              final safe SQL       execution policy + statement timeout
                                           ↓
                              SQLAlchemy/pyodbc execution
                                           ↓
                           bounded fetch (max_rows + 1)
                                           ↓
                     ResultSanitizer validates projection shape,
                     removes hidden columns, applies masks
                                           ↓
                                  SanitizedResult
```

The model proposes SQL; it does not choose its own profile, runtime tenant/user value, allowed objects, column operations, relationship allowlist, row limit, masking behavior, or execution permission.

## 4. The core product idea

The following descriptions are accurate to different degrees:

| Description | Accuracy | Reason |
| --- | --- | --- |
| Natural language → SQL | True but incomplete | Describes generation, not the v0.2 control and enforcement layers. |
| Developer-controlled Text-to-SQL | Strong | The developer controls the effective database surface and policy. |
| Query authorization layer for LLMs | Strong | Generated SQL is explicitly treated as untrusted and AST-authorized. |
| Semantic database scope for AI | Strong | QuerySpace combines selected physical metadata with semantic hints. |
| Secure database querying SDK | Use carefully | It provides meaningful defense-in-depth but cannot guarantee total database security. |
| AI-safe database interface | Use carefully | “Safe” needs qualification by the documented trust boundaries and limitations. |

The strongest factual product story is not “a better prompt.” It is **separation of probabilistic generation from deterministic authorization and policy enforcement**.

## 5. v0.1.0 baseline

### What v0.1.0 could do

The `v0.1.0` tag is a compact Text-to-T-SQL Python package:

1. `generate_query(question, engine, client, schema="dbo")` introspected all tables in one SQL Server schema.
2. Three catalog queries loaded tables, columns/PKs, and FKs for that schema.
3. `serialize_schema()` created deterministic prompt text.
4. an OpenAI-compatible client generated SQL from Persian or English intent.
5. a regex/string guard accepted one `SELECT` or `WITH ... SELECT` and rejected comments, extra semicolons, DML/DDL keywords, procedure-like access, `SELECT/OUTPUT INTO`, external access keywords, and four-part linked-server-style names.
6. `execute_select()` revalidated SQL and wrapped it in `SELECT TOP (max_rows) * FROM (...)` before execution.

### v0.1.0 architecture and API

- Public top-level exports: `DBConfig`, `Column`, `ForeignKey`, `Table`, `load_config`, `make_engine`, `test_connection`, and `__version__`.
- Generation/execution helpers existed in `querysmith.pipeline` but were not top-level exports.
- Schema model: simple mutable dataclasses for columns, FKs, and tables.
- Scope: one schema name at a time, defaulting to `dbo`.
- Introspection: whole-schema, not selected-table.
- LLM context: physical tables, data types, PK/nullability markers, and FKs.
- Validation: regex/string based, not parser/AST based.
- Authorization: no table/column allowlist beyond the prompt; the guard did not verify referenced identifiers against the schema it sent to the model.
- Relationships: prompt guidance only; not an authorization constraint.
- Execution: guarded raw SQL with a wrapper row limit; returned `list[dict]`.
- Tests: 46 test functions at the tag.

### v0.1.0 security boundary and limitations

The v0.1 guard reduced obvious read/write risk but was not a database authorization layer. It did not establish identifier lineage through aliases/CTEs/subqueries, enforce per-column operations, enforce declared relationships, inject tenant predicates, select an access profile, mask results, or verify the final query against an immutable scope. Database permissions and caller-side review remained essential.

## 6. v0.2.0 feature ledger

Status meanings:

- ✅ Implemented: present in implementation and exercised by tests.
- 🟡 Partially implemented: useful behavior exists, but the broad concept needs qualification.
- 📋 Planned/documented: described as intended without a complete enforcement implementation.
- ❌ Not present: no relevant implementation found.

| Capability | Status | Actual behavior and proof |
| --- | --- | --- |
| QuerySpace | ✅ | Immutable developer scope over selected tables, relationships, default column policy, and execution policy. `models.py`; `test_query_space.py`. |
| Custom table scopes | ✅ | `TableSpec(TableRef(...))` selects exact physical tables. `resolver.py`; `test_resolver.py`. |
| Multiple schemas | ✅ | Fully qualified `TableRef(schema, table)` and same short name across schemas are supported. `test_query_space_integration.py`; live integration test. |
| TableSpec | ✅ | Declares table identity, selected columns, aliases, descriptions, synonyms, rules, profiles, and required filters. |
| ColumnSpec | ✅ | Declares physical/semantic metadata, allow/deny/access level, capabilities, sensitivity, examples, and per-profile access. |
| RelationshipSpec | ✅ | Strict relationships authorize equality joins; non-strict relationships are semantic unless unlisted joins are enabled. `test_authorization.py`. |
| ExecutionPolicy | ✅ | Enforces max rows, execution on/off, wildcard policy, qualification, join count/types, subquery/CTE/cross-join settings, timeout, and mandatory filters. |
| Selective introspection | ✅ | Three parameterized catalog queries read only requested table pairs; requests are unique, non-empty, and capped at 500. `introspector.py`; `test_introspector.py`. |
| CatalogResolver / resolved spaces | ✅ | Merges physical catalog truth with developer semantic intent and fails on missing/incompatible declarations without mutating input. |
| Column allow/deny | ✅ | Default custom scope is deny; explicit allow mode includes catalog columns except explicit denials. Denied columns do not enter the effective user surface. |
| Protected/policy-only columns | ✅ | Kept in trusted resolved metadata, omitted from model context, rejected in generated SQL, available only to policy injection for filter/join use. |
| Semantic metadata | ✅ | Aliases, synonyms, descriptions, semantic types, units, examples, warnings, sensitivity, and capabilities are validated and serialized as hints. |
| Table/column descriptions | ✅ | Included in deterministic context with bounded lengths. |
| Relationships | ✅ | Catalog FKs inside the selected allowed scope and validated manual relationships are resolved; strict joins are authorized. |
| Business rules | 🟡 | References are validated and rule text reaches the LLM, but `RuleEnforcement` only has `ADVISORY`; there is no executable rule DSL. |
| AST-based SQL authorization | ✅ | `sqlglot` T-SQL parser plus lexical scopes and column lineage. `authorization.py`; authorization/adversarial tests. |
| Table authorization | ✅ | Every physical source, including set-operation/subquery branches, is checked against the active scope/profile. |
| Column authorization | ✅ | Physical lineage is checked across direct columns, expressions, aliases, CTEs, derived tables, correlations, and set operations. |
| Operation authorization | ✅ | Independent `SELECT`, `FILTER`, `SORT`, `GROUP`, `AGGREGATE`, and `JOIN` capabilities. |
| Relationship validation | ✅ | Strict equality relationship matching, join-type policy, and fail-closed handling for OR/non-equality/implicit joins. |
| Mandatory policy enforcement | ✅ | Typed predicates from static values or trusted runtime context are parameterized and injected into each applicable physical occurrence. |
| SQL/TOP limit enforcement | ✅ | AST adds or reduces T-SQL `TOP`; scalar aggregates without grouping skip TOP; result fetch still uses `max_rows + 1` for truncation detection. |
| DML/DDL prevention | ✅ | Parser accepts one `sqlglot.exp.Query`; write/DDL/procedure/external sources are rejected. SQL Server read-only credentials remain required defense-in-depth. |
| Legacy compatibility | 🟡 | Schema-based generation and legacy table adaptation remain. Raw `execute_select(engine, sql)` compatibility is intentionally broken: v0.2 requires an active resolved/profiled QuerySpace and returns `SanitizedResult`. |
| Execution safety | ✅ | Execution enable flag, authorized-artifact boundary, limits, shape constraints, timeout option/error wrapping, bounded fetch, and sanitization. Driver-level timeout behavior is deployment-dependent. |
| Schema drift detection | 🟡 | Resolution detects missing tables/columns and incompatible type/nullability/relationship metadata at resolution time. There is no background/continuous drift monitor; a long-lived resolved space must be refreshed by the host. |
| Access profiles | ✅ | Profile-aware table availability, operation capabilities, visibility, masking, and required filters. Missing/unknown profiles fail closed when profiles are declared. |
| Result masking and hiding | ✅ | FULL, PARTIAL, and CONSTANT masks; hidden output removal; transformed masked/hidden expressions are rejected. |
| Structured audit logging | ✅ | Lifecycle events, request IDs, literal-redacted SQL, parameter names, decisions, durations, and row counts. Default backend uses Python logging; durable audit storage is host responsibility. |
| Django adapter | ✅ | Optional Django 4.2+ adapter converts model metadata to QuerySpace/catalog objects and relationships. `test_django_adapter.py`. |
| PostgreSQL/MySQL/SQLite | ❌ | No dialect adapters; parsing, introspection, generation, and execution behavior target SQL Server/T-SQL. |
| Automatic query-cost planning | ❌ | No query optimizer/cost estimator. Join count, shape, timeout, and row limits are not full cost control. |
| Enforced arbitrary prose business rules | ❌ | Prose is advisory unless represented by a typed policy. |

## 7. Important v0.2.0 features in problem/how/benefit/example/proof form

### Feature: selective, multi-schema QuerySpace

**Problem:** Sending an LLM an entire schema exposes unnecessary metadata and leaves scope implicit.  
**How it works:** Developers declare fully qualified `TableRef`s, selected `ColumnSpec`s, and relationships. `SQLServerIntrospector` reads only those table pairs and `CatalogResolver` merges catalog truth with declarations.  
**Developer benefit:** Least-privilege context, smaller prompts, explicit boundaries, and support for use cases spanning schemas.  
**Example:** expose `Sales.Orders` and `CRM.Customers` but not payroll or internal-note columns.  
**Proof:** `models.py`, `introspector.py`, `resolver.py`; `test_query_space.py`, `test_introspector.py`, `test_query_space_integration.py`.

### Feature: semantic context separated from physical identifiers

**Problem:** Physical database names rarely match user vocabulary, particularly across Persian and English.  
**How it works:** Aliases, synonyms, descriptions, semantic types, units, examples, warnings, and advisory rules are clearly labeled as hints, while the context tells the model to emit physical identifiers.  
**Developer benefit:** Better intent grounding without pretending aliases are SQL names or weakening authorization.  
**Example:** map “مبلغ سفارش” / “order total” to physical `Sales.Orders.TotalDue`.  
**Proof:** `semantic.py`, `context.py`; `test_context.py`, `test_semantic.py`.

### Feature: per-operation column capabilities

**Problem:** A column may be safe for filtering or joining but unsafe to display, group, or aggregate. A single boolean “allowed” is too coarse.  
**How it works:** Each effective column has independent select/filter/sort/group/aggregate/join capabilities; AST lineage maps every use back to physical columns.  
**Developer benefit:** More precise least privilege and fewer accidental data exposures.  
**Example:** an internal status can be filterable but not selectable; a currency can be aggregatable but not joinable.  
**Proof:** `authorization.py`; `test_authorization.py`, `test_security_audit_phase56.py`.

### Feature: deterministic SQL authorization

**Problem:** Prompt instructions are not an authorization boundary.  
**How it works:** SQLGlot parses one T-SQL query, resolves scopes and lineage, and checks physical sources, columns, operations, relationships, wildcards, and shape.  
**Developer benefit:** Model output is treated as untrusted input; policy is enforced after generation.  
**Example:** a CTE that renames a hidden column is still rejected because lineage points to the hidden physical column.  
**Proof:** `authorization.py`; `test_authorization.py`, `test_adversarial_security.py`.

### Feature: mandatory row-policy injection

**Problem:** Asking a model to remember `TenantID = current_tenant` is bypassable and can leak cross-tenant rows.  
**How it works:** Host-supplied `runtime_context` is validated before generation. Typed filters are added as bound parameters to every physical occurrence; LEFT JOIN nullable-side predicates go in `ON`; unsafe RIGHT/FULL cases fail closed. The final AST is re-authorized.  
**Developer benefit:** Tenant/user/deletion filters do not depend on prompt compliance.  
**Example:** every `Sales.Orders` occurrence receives `TenantID = :qs_policy_...`.  
**Proof:** `policy.py`; `test_row_level_policy_hardened.py`, `test_policy_engine.py`.

### Feature: access profiles and result policy

**Problem:** Different application roles need different table, operation, visibility, and masking policies.  
**How it works:** The host selects a declared profile. The profile resolver computes effective capabilities and result access before context generation; the sanitizer hides or masks authorized projections after execution.  
**Developer benefit:** One logical QuerySpace can serve public, analyst, and internal experiences without letting the question choose the privilege level.  
**Example:** national ID hidden for public, fully masked for analyst, suffix-visible for internal.  
**Proof:** `profiles.py`, `sanitizer.py`; `test_profiles_and_sanitizer.py`, `test_security_audit_phase56.py`.

### Feature: execution boundary and auditability

**Problem:** Authorized SQL can be altered or confused with candidate SQL between checking and execution.  
**How it works:** `PolicyEngine` returns a frozen `AuthorizedQuery` containing final SQL, bound parameters, report, and applied policies. Execution accepts that artifact and returns a `SanitizedResult`; optional audit logging records lifecycle decisions.  
**Developer benefit:** Cleaner separation between proposal, authorization, execution, and returned data.  
**Example:** an authorization failure occurs before any connection is opened; successful execution uses only the policy-rewritten SQL and parameters.  
**Proof:** `pipeline.py`, `policy.py`, `audit.py`; pipeline and security audit tests.

## 8. v0.1.0 → v0.2.0 comparison

| Area | v0.1.0 | v0.2.0 candidate | Why it matters |
| --- | --- | --- | --- |
| Database scope | Whole named schema | Developer-selected QuerySpace | Reduces exposed metadata and makes scope explicit. |
| Schema assumptions | One schema, default `dbo` | Fully qualified tables across schemas | Real apps often span domain schemas. |
| Developer control | Prompt/schema choice | Tables, columns, capabilities, relationships, profiles, policies, limits | Moves control out of the LLM. |
| Tables | All introspected tables in schema | Exact table allowlist; profile table availability | Least privilege. |
| Columns | All schema columns sent to model | Deny-by-default custom scope, explicit denial, policy-only, per-profile rules | Better data minimization. |
| Relationships | FK text in prompt | Catalog/manual relationships plus strict AST enforcement | Joins become authorized behavior. |
| SQL validation | Regex/string checks | Parser + AST + lexical scopes/lineage | Handles aliases, CTEs, subqueries, expressions, and unions structurally. |
| Security model | Read-only keyword guard | Read-only parser, identifier/operation/relationship/profile/shape authorization, policy rewrite, result policy | Defense is broader and more deterministic. |
| Policy enforcement | None | Typed mandatory filters with bound parameters and final re-authorization | Row access no longer depends on model compliance. |
| Introspection | Whole-schema queries | Three selected-table parameterized queries, max 500 | Smaller metadata surface and bounded parameter count. |
| LLM context | Physical schema + FK markers | Effective physical scope + separated semantic hints/capabilities/rules | Better relevance and less privilege disclosure. |
| Execution control | Raw string guard + wrapper TOP | Active QuerySpace required; execution flag, AST TOP, query shape, timeout, bounded fetch | Stronger execution contract. |
| Results | `list[dict]` | `SanitizedResult` with masking/hiding/truncation metadata | Result policy becomes explicit. |
| API design | Small schema-based helpers | QuerySpace/resolver/context/authorization/policy/profile/sanitizer/audit layers plus facade | More capable but more complex. |
| Backward compatibility | N/A | Schema-based generation retained; raw execution path changed | Migration is partial, not drop-in for execution callers. |
| Extensibility | LLM protocol and SQLAlchemy engine | Adds custom catalog introspector protocol, profiles, Django adapter, audit logger protocol, semantic models | Easier integration with application architecture. |
| Tests | 46 functions | 244 collected test functions / 281 executed cases locally, plus 6 live SQL Server tests | Much broader behavior and adversarial coverage. |

### Biggest changes, ranked by developer significance

1. **AST authorization replaces regex-only safety** and validates actual tables, columns, operations, scopes, and joins.
2. **QuerySpace creates a developer-owned least-privilege database surface**, including multi-schema selection and deny-by-default columns.
3. **Mandatory row filters are parameterized and injected after generation**, then the final SQL is re-authorized.
4. **Access profiles and result sanitization** add role-specific capabilities, hiding, and masking.
5. **Semantic metadata and per-operation capabilities** improve model grounding while remaining enforceable after generation.
6. **Execution policies and the AuthorizedQuery boundary** add shape, timeout, row, and execution controls.
7. **Selective introspection, Django conversion, structured audit events, and live SQL Server CI assets** make the library more application-ready.

## 9. Real demonstration scenarios

The expected SQL descriptions below are concepts, not guarantees of exact model wording.

| # | Scenario | Developer configuration | User question | QuerySmith behavior / expected SQL concept | Feature proved | Visual potential |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Basic English analytics | One allowed orders table with ID/date/total | “Show the 10 largest orders.” | Context → T-SQL over the allowed table; authorization; TOP no greater than policy | Basic NL→T-SQL and limit | Question, generated SQL, green authorization report. |
| 2 | Persian request | Persian synonyms for user/person fields | “کاربرانی با نام سینا را نشان بده” | LLM maps Persian intent to physical identifiers; same authorization path | Persian prompt support + semantics | Persian input transforms into physical T-SQL. |
| 3 | Cross-schema user roles | `UPM.Users`, `UPM.UserRoles`, `UPM.Roles` plus strict relationships | “What roles does user Sina have?” | Multi-table equality joins must match declared relationships | Multi-table strict joins | Three-table diagram and highlighted join edges. |
| 4 | Cross-domain schemas | `UPM.Users` and `Cor.Unit`/permission bridge | “List users and their permitted units.” | Fully qualified sources across schemas are authorized | Multi-schema QuerySpace | Color-code schema prefixes. |
| 5 | Narrow table scope | Only customer/orders tables selected from a larger DB | “List employee salaries.” | Any model SQL referencing payroll/employee tables is rejected | Table allowlist | Scope window versus blocked out-of-scope table. |
| 6 | Hidden secret column | `SecretToken` or `InternalNote` denied | “Show customer secret tokens.” | Column absent from context and rejected if generated anyway | Denied columns | Column disappears from prompt, denial code appears. |
| 7 | Policy-only tenant column | `TenantID` policy-only + `RequiredFilter(value_from_context="tenant_id")` | “Show my orders.” | Model cannot query TenantID directly; injector adds a bound tenant predicate | Row-level policy | Before/after AST SQL with parameter placeholder. |
| 8 | Profile switch | public/analyst/internal result policies | Same national-ID query under each profile | Public denied/hidden; analyst masked; internal may show only permitted partial mask | Access profiles + masking | Three terminal panes with different results. |
| 9 | Invalid relationship | Two allowed tables but no matching strict relationship | Model joins on an unrelated pair | `RelationshipViolationError`; no DB connection | Relationship authorization | Red join edge, deterministic denial. |
| 10 | Destructive prompt/manual SQL | `/sql DELETE FROM ...` or user asks to drop a table | Parser rejects non-query statement before execution | Read-only AST parser | DML/DDL prevention | Red “authorization denied,” no DB activity. |
| 11 | Alias/CTE bypass attempt | Hidden column in a profiled space | CTE renames hidden column and selects alias | Lineage resolves alias back to forbidden physical column | Anti-bypass lineage | Animate CTE alias tracing backward. |
| 12 | Wildcard handling | Default `allow_select_star=False` | SQL candidate uses `SELECT *`; comparison uses `COUNT(*)` | Projection star rejected; unqualified count star accepted | Fine-grained wildcard policy | Side-by-side red/green SQL. |
| 13 | Query limit enforcement | `ExecutionPolicy(max_rows=50)` | “Show every activity log.” | Existing TOP is reduced or TOP 50 added; sanitizer detects truncation | AST TOP and result bound | TOP value visibly changes. |
| 14 | LEFT JOIN row policy | Tenant/deletion policy on nullable joined table | Query includes a LEFT JOIN | Policy predicate is injected into `ON`, preserving outer-join semantics | Safe policy rewrite | AST/SQL diff focusing on ON vs WHERE. |
| 15 | Unsafe FULL/RIGHT rewrite | Mandatory policy with FULL/RIGHT JOIN | Model proposes unsupported outer join shape | Fails closed with `OuterJoinRewriteError` | Conservative failure | “Cannot prove safe” denial is a credible security demo. |
| 16 | Schema drift before generation | Declared table/column renamed or type changed in SQL Server | Any question | Catalog resolution raises typed error before LLM call/execution | Resolution-time drift detection | Database migration then immediate typed failure. |
| 17 | Execution disabled | `ExecutionPolicy(allow_execution=False)` | Valid analytics question | SQL can be previewed, but execution request is refused | Preview/control separation | Toggle preview mode in terminal. |
| 18 | Interactive repository playground | `main.py` 15-table UPM/Cor QuerySpace, 13 relationships, three profiles | Persian/English municipal/user question | REPL shows final SQL, report, policies, masks, or denials | Integrated v0.2 showcase | Already designed for terminal capture. |

The strongest ready-made demo asset is `main.py`: it declares 15 tables across `UPM` and `Cor`, 13 relationships, public/analyst/internal profiles, row filters, a 50-row policy, and commands for profile switching, execution toggling, raw SQL testing, and authorization reports.

## 10. Verified developer code examples

These snippets use the real v0.2 API. They omit application-specific error handling.

### Minimal schema-compatible generation

With DB and LLM environment variables configured:

```python
from querysmith import ask

sql = ask("List active customers", schema="Sales")
print(sql)
```

This preserves the original schema-based generation style. It does not execute unless `execute=True`.

### Recommended v0.2 setup

```python
from querysmith import (
    CatalogResolver, ColumnSpec, QuerySpace, SQLServerIntrospector,
    TableRef, TableSpec, ask, load_config, make_engine,
)

engine = make_engine(load_config())
space = QuerySpace([
    TableSpec(
        TableRef("Sales", "Orders"),
        columns=[ColumnSpec("OrderID"), ColumnSpec("TotalDue")],
    )
])
resolved = CatalogResolver(SQLServerIntrospector(engine)).resolve(space)
sql = ask("Show the largest orders", query_space=resolved)
```

### Custom deny-by-default QuerySpace

```python
from querysmith import ColumnSpec, QuerySpace, TableRef, TableSpec

space = QuerySpace([
    TableSpec(
        TableRef("Sales", "Customer"),
        columns=[
            ColumnSpec("CustomerID"),
            ColumnSpec("DisplayName", alias="customer_name"),
            ColumnSpec("SecretToken", allowed=False),
        ],
    )
])
```

Unlisted catalog columns are omitted because a custom QuerySpace defaults to `DefaultColumnPolicy.DENY`.

### Multi-schema QuerySpace and relationship

```python
from querysmith import ColumnSpec, QuerySpace, RelationshipSpec, TableRef, TableSpec

orders = TableRef("Sales", "Orders")
customers = TableRef("CRM", "Customers")
space = QuerySpace(
    tables=[
        TableSpec(orders, columns=[ColumnSpec("CustomerID"), ColumnSpec("TotalDue")]),
        TableSpec(customers, columns=[ColumnSpec("CustomerID"), ColumnSpec("Name")]),
    ],
    relationships=[RelationshipSpec(orders, "CustomerID", customers, "CustomerID")],
)
```

### Independent column restrictions

```python
from querysmith import ColumnCapabilities, ColumnSpec

status = ColumnSpec(
    "InternalStatus",
    capabilities=ColumnCapabilities(
        selectable=False,
        filterable=True,
        sortable=False,
        groupable=False,
        aggregatable=False,
        joinable=False,
    ),
)
```

### Profile-specific masking

```python
from querysmith import ColumnAccess, ColumnSpec, MaskingPolicy, ResultAccess

national_id = ColumnSpec(
    "NationalID",
    profiles={
        "public": ColumnAccess.deny(),
        "analyst": ColumnAccess(
            result_access=ResultAccess.MASKED,
            masking=MaskingPolicy.full(),
        ),
        "internal": ColumnAccess(
            result_access=ResultAccess.MASKED,
            masking=MaskingPolicy.partial_suffix(4),
        ),
    },
)
```

### Mandatory runtime row policy

```python
from querysmith import ColumnAccess, ColumnSpec, RequiredFilter, TableRef, TableSpec

orders = TableSpec(
    TableRef("Sales", "Orders"),
    columns=[
        ColumnSpec("OrderID"),
        ColumnSpec("TotalDue"),
        ColumnSpec("TenantID", access=ColumnAccess.POLICY_ONLY),
    ],
    required_filters=[
        RequiredFilter(column="TenantID", value_from_context="tenant_id")
    ],
)
```

Call it with trusted host context, never a value extracted from the user’s question:

```python
sql = ask(
    "Show my orders",
    query_space=resolved_space,
    runtime_context={"tenant_id": authenticated_tenant_id},
)
```

### Explicit authorization and execution

```python
from querysmith import (
    OpenAICompatibleClient, authorize_query_in_space,
    execute_authorized_query,
)

authorized = authorize_query_in_space(
    "Show my orders",
    resolved_space,
    OpenAICompatibleClient(),
    runtime_context={"tenant_id": 42},
)
result = execute_authorized_query(
    engine,
    authorized,
    resolved_space,
    runtime_context={"tenant_id": 42},
)
print(result.rows)
```

### Backward-compatible v0.1-style generation

```python
from querysmith.llm import OpenAICompatibleClient
from querysmith.pipeline import generate_query

sql = generate_query(
    "Show recent orders",
    engine,
    OpenAICompatibleClient(),
    schema="Sales",
)
```

This generation facade remains. The old execution call `execute_select(engine, sql)` does **not**: v0.2 fails closed unless a `ResolvedQuerySpace` or `ProfiledQuerySpace` is supplied.

### Public API surface map

`querysmith.__init__` exposes a broad v0.2 surface. For future educational content, group it rather than presenting one undifferentiated import list:

- **Primary facade:** `ask`, `authorize_query_in_space`, `execute_authorized_query`, `execute_select`.
- **Scope and catalog:** `QuerySpace`, `ResolvedQuerySpace`, `ProfiledQuerySpace`, `TableRef`, `TableSpec`, `ColumnSpec`, `RelationshipSpec`, `CatalogSnapshot`, `CatalogTable`, `CatalogColumn`, `CatalogResolver`, `SQLServerIntrospector`, `inspect_tables`.
- **Policy and authorization:** `ExecutionPolicy`, `RequiredFilter`, `MandatoryFilterPolicy`, `PolicyEngine`, `AuthorizedQuery`, `AuthorizationReport`, `AuthorizationErrorCode`, `ColumnCapabilities`, `ColumnAccessLevel`, `FilterOperator`, `JoinType` and typed authorization/runtime exceptions.
- **Profiles and results:** `AccessProfile`, `TableAccess`, `ColumnAccess`, `ResultAccess`, `MaskingPolicy`, `MaskingMode`, `AccessProfileResolver`, `ResultSanitizer`, `SanitizedResult`.
- **Semantic context:** `ContextBuilder`, `ContextBuilderOptions`, `BusinessRule`, `SemanticType`, `DataSensitivity`, `SemanticColumnSpec`, `SemanticTableSpec`, `SemanticCatalog` and semantic validation errors.
- **Connectivity and integrations:** `DBConfig`, `load_config`, `make_engine`, `test_connection`, `LLMClient`, `OpenAICompatibleClient`, `django_models_to_query_space`, `DjangoCatalogIntrospector`, `parse_db_table`.
- **Audit:** `AuditEvent`, `AuditLogger`, `AuditLoggingPolicy`, `PythonLoggingAuditLogger`, `NullAuditLogger`.

Some implemented helpers are module-level rather than top-level public exports: `querysmith.pipeline.generate_query`, `generate_query_in_space`, and `resolve_query_space`; `querysmith.authorization.SQLParser` and `SQLAuthorizer`; `querysmith.audit.redact_sql_literals`; and `querysmith.db.build_url`. Future README/video examples should avoid implying that these can all be imported directly from `querysmith`.

## 11. Security story

### Verified guarantees within the implemented application layer

- Candidate SQL is parsed as T-SQL and must contain exactly one read-only `Query` statement.
- Comments, `SELECT INTO`, T-SQL system variables, physical table functions/external sources, and a denylist of dangerous metadata/external functions are rejected.
- Database/server-qualified sources are rejected; schema qualification is required by default.
- Physical tables must belong to the active resolved QuerySpace and profile.
- Columns are resolved through SQL scopes/lineage and authorized independently for projection, filter, sort, group, aggregate, and join operations.
- Ambiguous unqualified columns fail closed.
- `SELECT *`, `table.*`, and derived wildcard projections are denied by default; unqualified `COUNT(*)` is allowed. Even when star is enabled, every physical source column must be selectable and there can be no denied columns.
- Strict relationship joins require direct column equality matching a declared relationship; OR, non-equality cross-source predicates, predicate-free joins, and implicit comma joins fail closed unless an explicit policy supports the relevant shape.
- Query shape policies enforce join count and settings for CTEs, subqueries, cross joins, and join types.
- Missing/unknown access profiles fail before model generation when profile rules exist.
- Trusted runtime-context keys/values are validated before the model call; raw SQL objects, callables, invalid scalar/collection shapes, empty `IN`, and `IN` collections over 1,000 are rejected.
- Mandatory filters are inserted as AST placeholders and passed separately as bound parameters; values are not interpolated into SQL.
- Policies are applied to repeated/self-join occurrences, CTEs, subqueries, and set-operation branches. LEFT JOIN nullable-side filters are placed in `ON`; unprovable RIGHT/FULL cases fail closed.
- The original AST is copied. Rewritten SQL is parsed and fully authorized again, and its physical table/column set must equal the original set plus trusted policy columns.
- `max_rows` is enforced both by an AST TOP limit and bounded result fetching/sanitization.
- Result projection metadata prevents hidden/masked leaf columns from being exposed via expressions; authorized masks and hidden-column removal run after execution.
- Authorization failures occur before connection execution in the tested pipeline.

### Layering

v0.1 used string/regex checks. v0.2’s `validate_safe_select()` is a compatibility facade over `SQLParser` and optional `SQLAuthorizer`; primary v0.2 enforcement is parser/AST based. Prompt instructions still exist, but they are guidance and early filtering—not the authorization boundary.

### What QuerySmith does not guarantee

- It is not “100% secure,” formally verified, or a replacement for least-privilege SQL Server credentials.
- It cannot guarantee the model’s SQL is correct, efficient, semantically appropriate, or free of expensive plans.
- It supports only SQL Server/T-SQL; portability claims are unsafe.
- It does not prevent all abuse at the application perimeter. Authentication, request authorization, rate limiting, durable audit storage, abuse detection, network controls, secret management, and user/session management belong to the host.
- `max_rows`, `max_joins`, and timeout settings are not a complete resource governor. The database must enforce CPU, memory, lock, concurrency, and statement-resource limits.
- Statement timeout uses SQLAlchemy/driver execution options and error wrapping. Actual cancellation behavior depends on the SQLAlchemy/pyodbc/ODBC deployment; the live test suite was not run in this research environment.
- Schema drift is detected when a developer QuerySpace is resolved, not continuously. Long-lived resolved scopes should be refreshed after migrations.
- Semantic descriptions and `BusinessRule` prose are advisory. Only typed capabilities and policies are enforceable.
- The host chooses the access profile and runtime context. If the host supplies an incorrect privileged profile or tenant ID, QuerySmith cannot infer the correct identity.
- `AuthorizedQuery` is a public dataclass, not a cryptographically sealed capability. Application code must treat it as an internal artifact returned by `PolicyEngine`/`authorize_query_in_space`, must not manually construct it from untrusted SQL, and must keep the artifact paired with the same effective QuerySpace/profile.
- `allow_select_star` defaults to false and that default is the recommended security posture. Its opt-in path checks base resolved columns; do not market or deploy wildcard projection with profile-specific hiding/masking without additional profile-aware verification and tests.
- Audit SQL literal redaction is useful but not a general secret scanner. Do not place credentials or sensitive free text in questions/log metadata.
- Result masking changes returned representation; it is not database encryption, tokenization, or irreversible anonymization.

### Safe trust-boundary statement

> QuerySmith treats LLM output as untrusted and applies deterministic application-layer authorization and policy enforcement before optional execution. Deploy it with read-only, least-privilege SQL Server credentials and normal application/database controls.

## 12. Differentiators from `prompt = schema + question; db.execute(llm(prompt))`

| Differentiator | QuerySmith approach | Why it matters |
| --- | --- | --- |
| Explicit scope | Developer declares exact QuerySpace | The model does not define its own database surface. |
| Selective physical verification | Resolve selected declarations against SQL Server | Fails early on missing/incompatible metadata. |
| Semantic/physical separation | Hints improve intent; emitted SQL still uses physical identifiers | Better grounding without confusing SQL authorization. |
| Least-privilege columns | Deny-by-default, denied, policy-only, per-profile | Reduces model context and output exposure. |
| Independent operations | Select/filter/sort/group/aggregate/join capabilities | “Can use” is not a single all-or-nothing permission. |
| Deterministic post-generation authorization | AST scopes and lineage | Prompt compliance is not trusted. |
| Relationship allowlist | Strict joins validated from physical endpoints | Blocks invented or misleading joins. |
| Host-owned row access | Parameterized AST filter injection from trusted context | Tenant/user isolation does not rely on the model. |
| Final re-authorization | Reparse and re-check transformed SQL | The transformation itself is verified. |
| Execution contract | Frozen final artifact, execution policy, bounded fetch | Candidate SQL and executable SQL are distinct. |
| Result policy | Projection validation, hidden removal, masking | Control continues after the database returns rows. |
| Profile isolation | Active profile chosen by host, context narrowed before LLM | Prompt injection cannot request a higher profile. |
| Auditability | Structured lifecycle events and machine-readable reports | Applications can record decisions and denials. |
| Reusable architecture | Protocols/adapters for LLM, catalog, Django, and audit logging | Fits application code better than a one-off script. |

## 13. Target audiences and best demonstrations

| Audience | Their problem | Why QuerySmith may help | Feature they care about | Best demo |
| --- | --- | --- | --- | --- |
| Python backend developers | Add NL analytics without building a policy pipeline from scratch | Packaged models, resolver, authorizer, execution helpers | QuerySpace + concise API | Minimal setup to authorized SQL. |
| AI application engineers | Model SQL is probabilistic and bypassable | Deterministic post-generation checks and policy injection | AST authorization | CTE/alias bypass blocked. |
| SQL Server SaaS teams | Tenant and role boundaries must survive prompt injection | Host-owned profiles/context and mandatory filters | Tenant predicate injection | Same query for two tenant contexts. |
| Internal-tool developers | Need fast natural-language reporting over a controlled subset | Selective scope and execution policy | Multi-schema scope | Two schemas, only approved tables. |
| Enterprise/application security teams | Need explainable allow/deny evidence | Error codes, reports, audit events, least-privilege scope | Authorization report | Blocked query with report and zero execution. |
| Data/platform teams | Physical schemas lack business language | Semantic metadata while catalog remains source of truth | Semantic QuerySpace | Persian/English synonyms to physical SQL. |
| Django teams on SQL Server | Duplicating model metadata is costly | Optional model-to-QuerySpace/catalog adapter | Django adapter | Convert selected models, then authorize. |
| Developers building assistants | User questions need controlled database access | Preview/execute separation and sanitized results | End-to-end `ask()` | Valid query, mask, and result in one flow. |

## 14. Marketing-safe claims

### Safe to claim

- “QuerySmith v0.2.0 is a Python 3.11+ Text-to-T-SQL library for Microsoft SQL Server.”
- “It accepts Persian and English questions through an OpenAI-compatible LLM workflow.”
- “Developers can define a QuerySpace containing selected tables across multiple SQL Server schemas.”
- “Generated SQL is parsed and authorized against developer-defined tables, columns, operation capabilities, and relationships.”
- “Mandatory row filters are injected as bound parameters outside the LLM and the rewritten SQL is authorized again.”
- “Access profiles can hide or mask returned columns and restrict table/column capabilities.”
- “The default custom QuerySpace is deny-by-default for undeclared columns.”
- “The repository includes adversarial tests for aliases, CTEs, subqueries, set operations, wildcards, hidden columns, relationships, profiles, and row-policy bypass attempts.”
- “The local non-integration suite passed 281 cases on 2026-08-07.”
- “v0.1.0 is on PyPI; the repository contains a local v0.2.0 candidate build.”

### Claim carefully

- “Safe SQL”: say “application-layer authorization and guarded execution,” not an absolute guarantee.
- “Row-level security”: say “mandatory application-layer row-policy injection,” not native SQL Server Row-Level Security.
- “Schema drift detection”: qualify as “detected when QuerySpace is resolved.”
- “Supports Persian”: it relies on model capability and semantic hints; it is not a dedicated Persian NLP model.
- “OpenAI support”: it uses an OpenAI-compatible API client; endpoint/model compatibility remains provider-specific.
- “Timeout enforcement”: driver/database behavior must be verified in the target deployment.
- “Backward compatible”: schema-based generation is retained, but raw execution semantics and return type changed.
- “Business rules”: prose is validated and sent as advisory context; it is not enforced unless translated into typed policy.
- “Audit logging protects secrets”: SQL literals are redacted by default; this is not general DLP.
- “v0.2.0 release”: not until it is tagged/published; today it is a candidate/unreleased working tree.

### Do not claim

- “100% secure,” “unhackable,” or “the AI can never access restricted data.”
- “Prevents every SQL injection.”
- “Works with every database” or “database agnostic.”
- “No database permissions needed.”
- “Eliminates the need for security review.”
- “Guarantees correct or optimized SQL.”
- “Automatic enterprise compliance.”
- “Native database row-level security.”
- “All business rules are enforced.”
- “Continuous schema drift monitoring.”
- “v0.2.0 is available on PyPI” before publication.
- “Every query times out after N seconds” without validating the actual driver/database deployment.

## 15. Raw factual hook concepts (not scripts)

| Hook concept | Visual proof |
| --- | --- |
| Text-to-SQL is easy; deciding what the SQL is allowed to do is the real work. | Candidate SQL followed by AST authorization report. |
| Your LLM should not choose which tables it can access. | Small QuerySpace beside a much larger schema. |
| Your AI should not decide its own access profile. | Prompt asks for internal profile; host-selected public profile still blocks it. |
| A schema in a prompt is context, not authorization. | v0.1-style prompt versus v0.2 post-generation denial. |
| A hidden column can still leak through an alias—unless you track lineage. | CTE rename attack traced back and rejected. |
| “Filterable” does not have to mean “selectable.” | Status column works in WHERE but fails in SELECT. |
| Tenant isolation should come from trusted context, not user wording. | Host tenant ID becomes a bound predicate. |
| The safest tenant filter is one the model never controls. | Before/after SQL AST injection. |
| The SQL you generate should not be the SQL you blindly execute. | Candidate → authorized artifact → execution. |
| One database can expose different surfaces to public, analyst, and internal users. | Same question, three profile outcomes. |
| Mask sensitive results after authorization, not with a prompt request. | National ID becomes a partial mask. |
| Cross-schema analytics does not require exposing the whole database. | Two selected tables from different schemas. |
| An invented join can produce believable but wrong data. | Wrong join rejected against strict relationship. |
| `SELECT *` and `COUNT(*)` are not the same risk. | Red/green side-by-side authorization. |
| A row limit should survive model output. | `TOP 5000` reduced to policy maximum. |
| A LEFT JOIN policy belongs in the right place. | Predicate injected into ON, not WHERE. |
| When a rewrite cannot be proved safe, failing closed is a feature. | FULL JOIN policy injection denial. |
| Database aliases help humans; physical identifiers still protect execution. | Persian alias maps to physical column, then authorizer checks it. |
| QuerySmith v0.2 moves from keyword guardrails to AST authorization. | v0.1 regex code beside v0.2 AST scopes. |
| The LLM proposes; the developer’s QuerySpace disposes. | Model output hits policy boundary. |
| A useful AI database interface needs controls before and after execution. | Scope/context on left, sanitizer on right. |
| Security evidence should be machine-readable. | `AuthorizationReport.model_dump_json()`. |
| A blocked query is only credible if the database never sees it. | Spy/no-connection test or terminal trace. |
| Semantic context can improve SQL without becoming SQL. | Synonym/description labels versus physical identifiers. |

## 16. Visual assets in the repository

### Ready to show

- `python -m pip install querysmith` for the currently public v0.1 package; use a local/source install for v0.2 until published.
- `python main.py` interactive v0.2 playground with profile, execution, raw SQL, report, help, and quit commands.
- The 15-table UPM/Cor QuerySpace and 13 declared relationships in `main.py`.
- Public/analyst/internal profile switching.
- Generated/final SQL and applied policy output.
- Authorization allowed/denied terminal panels and stable error codes.
- `/sql <query>` for deterministic manual authorization demos without an LLM.
- `AuthorizationReport` JSON serialization.
- `pytest` output: 281 passed, 6 deselected in the local verification run.
- `tests/test_adversarial_security.py` scenario names.
- `dist/querysmith-0.2.0-py3-none-any.whl` and source distribution as local build artifacts.
- Git tag `v0.1.0`, current version metadata `0.2.0`, and a diff showing the architecture expansion.
- README QuerySpace, semantic, row-policy, authorization, profile, and audit examples (after correcting drift noted below).
- Docker Compose and GitHub Actions SQL Server integration-test configuration.

### Would need a created visual

- A clean v0.1 regex guard → v0.2 AST authorization architecture animation.
- QuerySpace as a highlighted subset of a larger database diagram.
- Candidate SQL → policy injection → final authorization flow diagram.
- Alias/CTE lineage tracing animation.
- Three-profile result comparison graphic.
- LEFT JOIN ON-clause policy placement illustration.
- v0.1 versus v0.2 capability timeline.
- PyPI/GitHub release badge for v0.2 after publication.
- A concise multi-schema diagram using the UPM/Cor playground schema.
- Branded screenshots with credentials, hostnames, tenant values, and real personal data removed.

## 17. Installation and project metadata

| Field | Verified value | Notes |
| --- | --- | --- |
| Package/import name | `querysmith` | PyPI and Python package agree. |
| Current working-tree version | `0.2.0` | `pyproject.toml`, `src/querysmith/__init__.py`, and local distributions agree. |
| Previous public version | `0.1.0` | Git tag and PyPI release. |
| Python | `>=3.11` | Classifiers include 3.11, 3.12, 3.13. |
| Database | Microsoft SQL Server | T-SQL, SQLAlchemy `mssql+pyodbc`. |
| Question languages | Persian and English | Prompt/model-level support. |
| License | MIT | `LICENSE` and project metadata. |
| Maturity | Alpha | PyPI classifier; v0.2 currently unreleased. |
| Runtime dependencies | SQLAlchemy 2+, pyodbc, python-dotenv, sqlglot 25+, openai, langchain-openai | `sqlglot` is new relative to v0.1. |
| Optional dependency | Django 4.2+ | `[project.optional-dependencies].django`. |
| Install | `python -m pip install querysmith` | Installs public v0.1 today. For candidate v0.2 use source/editable install or local wheel. |
| Repository | `https://github.com/SinaQP/QuerySmith` | Public repository. |
| LLM config | API key plus optional compatible base URL/model | Key precedence: QuerySmith, AvalAI, OpenAI. Default base URL AvalAI; default model `gpt-4o-mini`. |
| DB config | host/server, optional port, DB, username/password, driver, trusted flag | Current loader still requires username/password even when trusted auth is enabled. |
| ODBC | System driver required separately | Code defaults to ODBC Driver 17; docs commonly suggest explicitly choosing Driver 18. |

Public verification links: [PyPI JSON/project metadata](https://pypi.org/pypi/querysmith/json) and [GitHub releases](https://github.com/SinaQP/QuerySmith/releases).

## 18. Developer experience assessment

### Strengths

- A minimal schema-based question is one `ask()` call after environment setup.
- Modern API names (`QuerySpace`, `TableSpec`, `ColumnSpec`, `ExecutionPolicy`) reflect the domain clearly.
- Dataclasses are frozen and validate aggressively, producing typed exceptions early.
- The LLM interface is a minimal protocol, making fake clients easy in tests.
- A custom catalog-introspector protocol enables resolution without requiring the concrete SQL Server introspector in every test/integration.
- Semantic context is deterministic and options can suppress examples.
- The active security decision is inspectable through `AuthorizedQuery` and `AuthorizationReport`.
- `SanitizedResult` exposes rows, columns, count, truncation, and profile, while supporting list-like iteration/indexing.
- The playground provides a ready terminal experience for profile/security demos.

### Friction and caveats

- Secure modern setup has real boilerplate: define scope, introspect/resolve, select profile/context, authorize, and execute.
- The top-level public API is very large in v0.2, which improves discoverability but makes the stable surface harder to communicate.
- Some useful helpers (`generate_query`, `generate_query_in_space`, `resolve_query_space`, `SQLParser`, `SQLAuthorizer`, `redact_sql_literals`, `build_url`) are not top-level exports, so examples must use module imports where needed.
- Environment configuration has provider aliases and DB aliases, but trusted authentication still requires username/password due to loader validation.
- The public PyPI install currently returns v0.1, not the local v0.2 candidate.
- The legacy execution behavior changed and README migration guidance is missing.
- Live SQL Server setup needs a separately installed ODBC driver and a reachable server/container.
- `requirements.txt` mixes runtime, test, and optional Django packages, while `pyproject.toml` separates them. Contributors should prefer editable extras.

### Quick video-friendly developer experience

The shortest convincing sequence is:

```text
define two TableSpecs → resolve against SQL Server → ask a question
→ show AuthorizedQuery/report → optionally execute → show SanitizedResult
```

For a no-LLM security clip, use `main.py`’s `/sql` command to submit allowed and denied T-SQL directly to the same policy engine.

## 19. Test-derived capabilities and edge cases

The non-live suite executed 281 cases successfully; six marked SQL Server integration tests were deselected. Important guarantees visible primarily or most clearly in tests include:

- Same short table name is allowed in different schemas; identity is case-insensitive and fully qualified.
- Selected introspection uses exactly three bounded parameterized catalog queries and rejects empty, duplicate, or over-500 table-ref requests.
- Resolution is idempotent for already-resolved spaces and does not mutate developer declarations.
- Alias/synonym collisions are normalized and rejected, including collision with undeclared physical columns.
- Sensitive columns cannot publish example values; restricted columns default to no operations.
- Semantic types are checked for compatibility with physical SQL types; units are limited to quantitative types.
- Capability enforcement survives CASE expressions, arithmetic, functions, HAVING, window partitions, output aliases, CTEs, derived tables, correlations, unions, intersections, and exceptions.
- An unqualified ambiguous column fails closed.
- Strict relationships work in either direction; correlated subqueries must also match a relationship.
- Explicit cross-join policy does not silently allow implicit comma joins.
- Policy injection preserves existing OR precedence, is idempotent, applies to self joins, and does not mutate the original AST.
- Existing lower TOP is preserved; excessive TOP is reduced; missing TOP is added; scalar aggregate counts avoid an unnecessary TOP.
- A malicious injector that changes tables or extra columns fails final validation.
- Profile escalation wording in the question does not change the host-selected profile.
- Missing/invalid runtime context fails before an LLM call.
- Contradictory tenant predicates and tautology-style evasions are rejected or receive the mandatory predicate.
- Hidden columns cannot be exposed through `HASHBYTES`, `REVERSE`, `SUBSTRING`, CTE aliasing, EXISTS, or NOT EXISTS.
- Transformed expressions over masked columns are rejected instead of returning an unmasked derivative.
- Duplicate output aliases and output-schema mismatches fail sanitization.
- FULL outer join with mandatory policy fails closed.
- Unit tests simulate generic and `HYT00` timeout errors as `QueryTimeoutError`.
- The live suite is designed to cover real multi-schema execution, forbidden table/column blocking, profile enforcement, tenant isolation, WAITFOR timeout, and truncation against SQL Server 2022.

## 20. Documentation and release drift

| Finding | Code/reality says | Docs/metadata says | Recommendation |
| --- | --- | --- | --- |
| Release state | Working tree/version/build say 0.2.0; only v0.1 tag/PyPI release | Changelog says Unreleased; README says preparing for first PyPI release | Replace with explicit “v0.2 unreleased candidate; v0.1 available on PyPI” until launch. |
| First public release | PyPI 0.1.0 exists | README still says “prepared for its first public PyPI release” | Remove stale statement. |
| Installation | `pip install querysmith` installs 0.1.0 today | README v0.2 features sit beside that install command | Add version-qualified source install/pre-release notice until v0.2 is published. |
| Legacy execution | `execute_select` now requires resolved/profiled QuerySpace and returns `SanitizedResult` | Minimal example says call `execute_select(engine, sql)` and implies raw list behavior | Replace with modern resolved-space execution example and migration note. |
| Changelog version | Candidate features are extensive and local version is 0.2.0 | All changes are under `Unreleased`, no `## 0.2.0` section/date | Cut a versioned changelog entry at release time. |
| Authorization report policies | `AuthorizedQuery.applied_policies` is populated; `AuthorizationReport.injected_policies` is currently constructed as empty | Changelog describes `AuthorizationReport.injected_policies` as enriched data | Either copy applied policies into the final report or document the field location accurately. |
| Error code table | Enum also includes group/sort/aggregate, policy bypass, and unsupported shape codes | README table lists only a subset | Label table “selected codes” or include the full enum. |
| Audit secret wording | Literal redaction and default no question/parameter values are implemented | README says sensitive literals and credentials are automatically redacted | Narrow to SQL literal redaction; do not imply general credential detection. |
| Timeout | Code configures timeout and wraps known error text; unit/live tests exist | README presents timeout enforcement without deployment caveat | State driver/database dependence and publish tested driver matrix. |
| Tests command | Current normal suite has integration markers and live prerequisites | README “full suite” command points only to adversarial file | Document unit, adversarial, and live integration commands separately. |
| Requirements | `pyproject.toml` makes Django optional and dev tools an extra | `requirements.txt` installs pytest and Django together with runtime packages | Clarify intended audience or split runtime/dev requirements. |
| Public API story | Many v0.2 names are top-level; some orchestration/parser helpers remain module-only | README mixes top-level and module imports without defining stability | Publish a small “recommended stable API” section. |
| Schema drift | Resolver catches drift only when invoked | “Schema drift detection” can sound continuous | Always qualify as resolution-time validation. |

## 21. Conceptual alternatives and where QuerySmith fits

| Alternative | Typical strength | Typical gap QuerySmith addresses |
| --- | --- | --- |
| Raw schema + prompt + execute | Fastest prototype | No deterministic identifier/profile/policy authorization or result policy. |
| Custom prompt engineering | Flexible and simple | Instructions remain probabilistic; every team rebuilds enforcement. |
| General database agents | Multi-step/tool autonomy | Often broader authority and more moving pieces than a narrow SQL Server query SDK. |
| Hand-written API/report endpoints | Strong explicit control | Each question/report must be designed and maintained in advance. |
| BI tools | Mature dashboards/governance | Different integration model; less suited to embedding custom NL query behavior in Python apps. |
| ORM filter builders | Typed application queries | Usually require structured filters rather than free-form Persian/English questions. |

QuerySmith fits between free-form LLM generation and hand-written endpoints: it preserves flexible questions while constraining SQL to an application-defined SQL Server surface. It should be positioned as an embeddable policy-aware SDK, not as a replacement for SQL Server permissions, BI governance, or general database administration.

## 22. Video content opportunity matrix

These are concepts/titles only, not scripts.

| Video idea | Core feature | Audience | Demo potential | Difficulty | Suggested length |
| --- | --- | --- | --- | --- | --- |
| What QuerySmith Actually Is | End-to-end controlled Text-to-SQL | General developers | High | Medium | 45–60s |
| QuerySmith v0.2.0 Candidate Overview | Release delta | Existing users | High | Medium | 30–45s |
| v0.1 Regex Guard vs v0.2 AST Authorization | Architecture evolution | Security/AI engineers | Very high | Medium | 30–45s |
| Build a Least-Privilege QuerySpace | Table/column scope | Backend developers | High | Low | 20–30s |
| Query Two SQL Server Schemas Safely | Multi-schema | Data/internal-tool teams | High | Medium | 20–30s |
| Persian Question to Physical T-SQL | Semantic synonyms | Persian developer community | Very high | Low | 15–20s |
| English Question to Authorized SQL | Basic flow | New users | High | Low | 15–20s |
| Why `SELECT *` Gets Blocked | Wildcard policy | Developers/security | Very high | Low | 10–15s |
| `COUNT(*)` Is Different | Fine-grained AST policy | SQL developers | High | Low | 10–15s |
| The CTE Alias Bypass Test | Column lineage | Security engineers | Very high | Medium | 20–30s |
| The LLM Cannot Choose “Internal” | Access-profile isolation | SaaS/security teams | Very high | Low | 15–20s |
| One Question, Three Profiles | Hide/mask/allow | Product/backend teams | Very high | Medium | 20–30s |
| Tenant Filter Outside the LLM | RequiredFilter injection | SaaS developers | Very high | Medium | 30–45s |
| LEFT JOIN Policy Injection Done Carefully | AST rewrite semantics | Advanced developers | High | High | 45–60s |
| Fail Closed on FULL JOIN | Conservative enforcement | Security engineers | High | Medium | 15–20s |
| Block a Destructive SQL Attempt | Read-only parser | General developers | Very high | Low | 10–15s |
| Stop an Invented Join | Strict relationships | Data developers | High | Medium | 20–30s |
| Filterable but Not Selectable | Operation capabilities | Security/backend teams | High | Low | 15–20s |
| From Candidate SQL to AuthorizedQuery | Execution boundary | Software architects | High | Medium | 30–45s |
| Authorization Report in JSON | Auditability | Enterprise developers | Medium | Low | 15–20s |
| QuerySmith in a Django SQL Server App | Django adapter | Django developers | Medium | Medium | 30–45s |
| Interactive `main.py` Playground Tour | Integrated repository demo | Contributors/users | Very high | Low | 45–60s |
| Open-Source Package Anatomy | PyPI/GitHub/tests/license | OSS audience | Medium | Low | 20–30s |
| 281 Tests and 28 Hostile Scenarios | Test/security credibility | Technical evaluators | High | Low | 20–30s |

## 23. Ranked stories

### Top five strongest things about QuerySmith overall

1. It treats model-generated SQL as untrusted and separates generation from deterministic authorization.
2. QuerySpace gives developers a least-privilege, multi-schema database surface instead of exposing a whole database implicitly.
3. Mandatory row policies come from trusted host context and are injected as parameters outside the LLM.
4. Column permissions are precise across operation, access profile, and returned-result behavior.
5. The complete boundary is inspectable: resolved scope, final SQL, parameters, applied policies, authorization report, sanitized result, and audit events.

### Top five strongest additions in v0.2.0

1. AST-based table/column/operation/relationship authorization with scope lineage.
2. QuerySpace, selective introspection, CatalogResolver, and multi-schema support.
3. Mandatory policy injection plus final SQL re-authorization.
4. Access profiles, hidden/masked results, and projection-aware sanitization.
5. Execution policies, immutable AuthorizedQuery, structured audit logging, and broad adversarial/integration tests.

### Best story by format

- **10–15 second video:** `SELECT *` blocked while `COUNT(*)` passes, or a destructive query denied.
- **20–30 second video:** same question under public/analyst/internal profiles, showing denial/full mask/partial mask.
- **45–60 second technical demo:** natural-language question → resolved QuerySpace context → candidate SQL → tenant filter/TOP injection → final report → sanitized result.
- **Launch announcement:** v0.1 keyword guard to v0.2 developer-controlled QuerySpace + AST authorization + policies/profiles.
- **Security-focused video:** prompt tries profile/tenant/CTE bypass; host-selected policy and lineage still deny or constrain it.
- **Developer-focused video:** define a small multi-schema QuerySpace, resolve it, and call `ask()` with a concise real API snippet.

## 24. Verification record

- [x] Current candidate version identified as 0.2.0 in code/build metadata.
- [x] Public release state separately verified: PyPI/tag 0.1.0 only.
- [x] v0.1.0 baseline read directly from tag `v0.1.0`.
- [x] v0.1 → v0.2 differences documented.
- [x] Implemented, partial, planned/documented, and absent behavior distinguished.
- [x] Public API examples use real import paths and signatures.
- [x] Security claims grounded in implementation and tests, with trust limits stated.
- [x] 18 demonstration scenarios identified.
- [x] 24 future video opportunities identified.
- [x] Developer pain points and target audiences documented.
- [x] Safe, careful, and prohibited claims separated.
- [x] Documentation/release inconsistencies reported.
- [x] No finished promotional script, storyboard, caption, voice-over, ad, or campaign created.
- [x] Local verification: `281 passed, 6 deselected` with `-m "not integration and not sqlserver"`.
- [ ] Live SQL Server tests executed in this research session. They require the external SQL Server/ODBC integration environment; repository assets and test implementations were inspected instead.

## 25. Repository evidence map

| Topic | Primary implementation | Primary tests/docs |
| --- | --- | --- |
| Version/package/config | `pyproject.toml`, `src/querysmith/__init__.py`, `config.py`, `db.py` | README, PyPI metadata |
| v0.1 baseline | Git tag `v0.1.0` | v0.1 tests and README at tag |
| QuerySpace/models | `models.py`, `semantic.py` | `test_query_space.py`, `test_semantic.py` |
| Selective catalog | `catalog.py`, `introspector.py`, `resolver.py` | `test_introspector.py`, `test_resolver.py` |
| LLM/context | `llm.py`, `context.py`, `serializer.py` | `test_llm.py`, `test_context.py`, `test_serializer.py` |
| SQL authorization | `authorization.py`, `guard.py`, `exceptions.py` | `test_authorization.py`, `test_guard.py`, `test_adversarial_security.py` |
| Row policies | `policy.py` | `test_policy_engine.py`, `test_row_level_policy_hardened.py` |
| Profiles/results | `profiles.py`, `sanitizer.py` | `test_profiles_and_sanitizer.py`, `test_security_audit_phase56.py` |
| Pipeline/execution | `pipeline.py` | `test_pipeline.py`, security audit tests |
| Audit | `audit.py` | pipeline/security tests and README |
| Django | `django_adapter.py` | `test_django_adapter.py` |
| Live SQL Server | `docker-compose.integration.yml`, CI workflow | `test_sqlserver_integration.py` |
| Integrated visual demo | `main.py` | terminal commands embedded in playground |

## 26. Final editorial guidance for future video-generating AIs

When turning this research into videos:

1. Lead with developer control and post-generation enforcement, not generic AI novelty.
2. Show both a successful path and a blocked path; QuerySmith’s value is clearest at the boundary.
3. Keep SQL Server/T-SQL visible so viewers do not infer cross-database support.
4. Say “v0.2.0 candidate/upcoming” until a v0.2 tag and PyPI release exist.
5. Keep business rules labeled advisory unless the demo uses a typed mandatory policy.
6. Show runtime tenant/profile values as host application inputs, never values extracted from the prompt.
7. Avoid absolute security language; pair application-layer guarantees with read-only SQL Server credentials and deployment controls.
8. Use exact public APIs from section 10 and correct the README drift before recording install/execution instructions.
