# Changelog

## [0.2.0] - 2026-08-08

### Added

- Added developer-defined `QuerySpace` scopes for selected tables across multiple
  SQL Server schemas, with selective catalog introspection and immutable resolved
  metadata.
- Added semantic table and column metadata, declarative access profiles, Django
  model adapters, structured authorization reports, and audit logging.
- Added execution policies for row limits, timeouts, query shapes, joins, result
  visibility, and masking.

### Changed

- Query generation and execution now resolve a developer-defined scope before the
  LLM is called and carry an immutable `AuthorizedQuery` across the execution
  boundary.
- Direct `execute_select()` calls now require an active resolved or profiled
  QuerySpace and fail closed when no scope is supplied.

### Compatibility

- Requires Python 3.11 or newer and supports Microsoft SQL Server T-SQL `SELECT`
  queries only.
- The schema-based `ask(..., schema=...)` and `generate_query(..., schema=...)`
  facades remain available for compatibility.

### Security

- Added AST-based T-SQL authorization for tables, columns, query scopes, and
  operation-level column capabilities.
- Added strict relationship validation and fail-closed join-shape policies.
- Added typed, parameterized mandatory policy injection, including safe `LEFT
  JOIN` handling and final SQL re-authorization.
- Restricted projection wildcards while preserving safe `COUNT(*)` behavior.
- Connected execution to the immutable final `AuthorizedQuery` artifact.
- **Phase 5 — Access Profiles**: Added profile-aware `AccessProfile`, `TableAccess`, `ColumnAccess`, `ResultAccess`, `MaskingPolicy`, and `AccessProfileResolver` for multi-tenant, role-based data access.
- **Phase 6 — Result Policy & Execution Safety**: Added `ResultSanitizer`, `SanitizedResult`, data masking (FULL, PARTIAL, CONSTANT), hidden column stripping, statement timeout enforcement, and execution safety shape checks (`max_joins`, `allow_subqueries`, `allow_ctes`, `allow_cross_join`).
- **Row-Level Access Policy & Mandatory Filter Injection**:
  - Enhanced `RequiredFilter` to support `EQ`, `NE`/`NOT_EQ`, and `IN` operators with strict typed validation.
  - Implemented fail-closed `validate_runtime_context` pre-validation, raising `MissingRuntimeContextError` for missing context keys and `InvalidRuntimeContextValueError` for type mismatches, empty collections, >1,000 collection items, or raw SQL objects/callables.
  - Implemented AST-based parameterization (`:qs_policy_...`) for mandatory policy injection across single/self joins, CTEs, subqueries, and `UNION`/`UNION ALL` branches.
  - Added fail-closed `OuterJoinRewriteError` for unsafe `RIGHT`/`FULL` join targets and `ConflictingMandatoryFilterError` for user predicates contradicting mandatory policies.
  - Hardened AST Rewriter to preserve AST immutability and perform second-pass re-authorization (`FinalSQLValidationError`).
  - Added comprehensive exception hierarchy subclassing `RowLevelPolicyError`, `SQLRewriteError`, `MandatoryPolicyError`, `PolicyInjectionError`, and `FinalAuthorizationError`.
- **Adversarial Security Test Suite**:
  - Implemented 28 hostile attack scenario tests covering CTE renames, alias bypasses, subqueries, set operations (`UNION`, `INTERSECT`, `EXCEPT`), `SELECT *`, ambiguous columns, hidden column filter functions (`HASHBYTES`, `REVERSE`, `SUBSTRING`), unlisted JOINs, profile escalation, mandatory filter removal/evasion, tautology evasion, mandatory filter contradictions, and `EXISTS`/`NOT EXISTS` subqueries.
- **Authorization Report & Error Codes**:
  - Enriched `AuthorizationReport` dataclass with `allowed`, `error_code`, `tables_used`, `columns_used` by operation (`SELECT`, `FILTER`, `SORT`, `GROUP`, `AGGREGATE`, `JOIN`), `access_profile`, `injected_policies`, `applied_masks`, `hidden_columns`, `relationships_used`, and `query_shape`.
  - Added full serialization support (`to_dict()`, `model_dump()`, `model_dump_json()`).
  - Added `AuthorizationErrorCode` enum for stable, machine-readable error codes.
- **Structured Audit Logging**:
  - Created `AuditEvent`, `AuditLogger` protocol, `PythonLoggingAuditLogger`, `NullAuditLogger`, and `AuditLoggingPolicy`.
  - Integrated audit logging across `ask()`, `authorize_query_in_space()`, `execute_select()`, and `execute_authorized_query()`.
  - Added request ID tracking and safe literal redaction (`redact_sql_literals`).
- **Live SQL Server Integration Testing**:
  - Added `docker-compose.integration.yml` (MSSQL 2022 image, port 14333, healthcheck) and `.env.integration.example`.
  - Implemented `tests/test_sqlserver_integration.py` covering real database execution, multi-schema queries, profile enforcement, tenant isolation, statement timeout (`WAITFOR DELAY`), and row limit truncation.
  - Added GitHub Actions workflow `.github/workflows/integration-sqlserver.yml` for automated CI testing.


This hardening can reject SQL that earlier versions accepted when it is ambiguous,
uses an undeclared operation capability or relationship, references a wildcard, or
cannot be rewritten and re-authorized safely.
