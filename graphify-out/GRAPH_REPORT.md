# Graph Report - QuerySmith  (2026-08-08)

## Corpus Check
- 46 files · ~53,100 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1218 nodes · 4949 edges · 54 communities (50 shown, 4 thin omitted)
- Extraction: 51% EXTRACTED · 49% INFERRED · 0% AMBIGUOUS · INFERRED: 2447 edges (avg confidence: 0.59)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c866e130`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Configuration Management
- Database Schema Metadata
- Query Execution and Generation
- SQL Safety Validation
- OpenAI Integration
- SQL Prompt Building
- Safe SQL Generation
- TableRef
- _validate_space
- FakeConnection
- test_multi_schema_query_space_flows_through_serializer_llm_and_guard
- models.py
- QuerySmith Core
- QuerySmith Framework
- ContextBuilder
- QuerySpaceValidationError
- CatalogSnapshot
- pytest
- FakeClient
- TableRef
- generate_query_in_space
- ask
- FakeResult
- SQLServerIntrospector
- ExecutionPolicy
- .resolve
- SanitizedResult
- ExecutionSafetyError
- test_multi_schema_query_space_flows_through_serializer_llm_and_guard
- AccessProfileResolver
- resolver.py
- QuerySpaceValidationError
- _validate_space
- PolicyEngine
- execute_select
- RequiredFilter
- test_table_full_name_and_schema_fields
- 18. Developer experience assessment
- SpyConnection
- AuthorizedQuery
- SemanticTableSpec
- FakeConnection
- _identifier_key
- AccessProfileError
- test_llm.py
- ask
- llm.py
- ColumnAccess
- DjangoCatalogIntrospector
- generate_query
- pytest
- AuditLogger
- CapturingClient
- .connect

## God Nodes (most connected - your core abstractions)
1. `TableRef` - 184 edges
2. `ResolvedQuerySpace` - 167 edges
3. `TableSpec` - 108 edges
4. `QuerySpace` - 106 edges
5. `ColumnSpec` - 104 edges
6. `ExecutionPolicy` - 96 edges
7. `PolicyEngine` - 90 edges
8. `CatalogResolver` - 89 edges
9. `CatalogTable` - 88 edges
10. `RelationshipSpec` - 86 edges

## Surprising Connections (you probably didn't know these)
- `test_not_eq_operator_alias_support()` --calls--> `RequiredFilter`  [INFERRED]
  tests/test_row_level_policy_hardened.py → src/querysmith/models.py
- `test_table_ref_uses_fully_qualified_case_insensitive_identity()` --calls--> `TableRef`  [INFERRED]
  tests/test_query_space.py → src/querysmith/models.py
- `DemoState` --uses--> `CatalogColumn`  [INFERRED]
  main.py → src/querysmith/catalog.py
- `DemoState` --uses--> `CatalogSnapshot`  [INFERRED]
  main.py → src/querysmith/catalog.py
- `DemoState` --uses--> `CatalogTable`  [INFERRED]
  main.py → src/querysmith/catalog.py

## Import Cycles
- None detected.

## Communities (54 total, 4 thin omitted)

### Community 0 - "Configuration Management"
Cohesion: 0.17
Nodes (23): execute_select(), Validate and execute a SELECT query with a conservative row limit., FakeClient, FakeEngine, _mandatory_policy_space(), Tests for QuerySmith pipeline helpers., _space(), test_ask_authorization_failure_prevents_connection() (+15 more)

### Community 1 - "Database Schema Metadata"
Cohesion: 0.10
Nodes (19): 12. Differentiators from `prompt = schema + question; db.execute(llm(prompt))`, 13. Target audiences and best demonstrations, 15. Raw factual hook concepts (not scripts), 17. Installation and project metadata, 19. Test-derived capabilities and edge cases, 1. Executive source of truth, 20. Documentation and release drift, 21. Conceptual alternatives and where QuerySmith fits (+11 more)

### Community 2 - "Query Execution and Generation"
Cohesion: 0.08
Nodes (20): Collection, Expression, Scope, Composition of immutable physical, semantic, and capability metadata., Original mutable table model retained for backward compatibility., ResolvedColumn, Table, _qualified_referenced_table() (+12 more)

### Community 3 - "SQL Safety Validation"
Cohesion: 0.15
Nodes (27): Parse one read-only T-SQL query and optionally authorize its QuerySpace use., validate_safe_select(), _capability_space(), _query_space(), Tests for SQL safety guardrails., test_accept_select_with_trailing_semicolon(), test_accept_simple_select(), test_accept_with_cte_select() (+19 more)

### Community 4 - "OpenAI Integration"
Cohesion: 0.12
Nodes (37): AliasConflictError, CatalogResolutionError, ColumnNotFoundError, ColumnTypeMismatchError, DefaultColumnPolicy, FilterOperator, ForbiddenColumnError, ForeignKey (+29 more)

### Community 5 - "SQL Prompt Building"
Cohesion: 0.10
Nodes (21): ChatOpenAI, OpenAIEmbeddings, OpenAICompatibleClient, OpenAI-compatible client with AvalAI defaults., Return a chat completion for the prompt., Return a LangChain chat model configured like this client., Return LangChain OpenAI-compatible embeddings., FakeChat (+13 more)

### Community 6 - "Safe SQL Generation"
Cohesion: 0.12
Nodes (11): FakeEngine, FakeConnection, FakeEngine, FakeResult, Any, Self, Tests for bounded exact-table SQL Server introspection., test_inspect_tables_uses_three_bounded_parameterized_queries() (+3 more)

### Community 7 - "TableRef"
Cohesion: 0.10
Nodes (5): CatalogSnapshot, Bounded catalog result for an exact set of requested tables., The schema-qualified identity of a SQL Server table., TableRef, Return physical metadata for exact requested identities.

### Community 8 - "_validate_space"
Cohesion: 0.13
Nodes (16): Logger, Process a natural language question through QuerySmith pipeline., run_question(), AuditEvent, AuditLoggingPolicy, NullAuditLogger, Any, PythonLoggingAuditLogger (+8 more)

### Community 9 - "FakeConnection"
Cohesion: 0.18
Nodes (36): AmbiguousColumnError, _Binding, ColumnOperationNotAllowedError, Raised when a column is used for a denied SQL operation., Raised when a column cannot be resolved to exactly one source., Raised when a join shape is disabled by execution policy., Raised when a join predicate does not match a strict relationship., Raised when projection wildcards are disabled or invalid. (+28 more)

### Community 10 - "test_multi_schema_query_space_flows_through_serializer_llm_and_guard"
Cohesion: 0.06
Nodes (43): build_engine(), build_llm_client(), DemoState, format_terminal_table(), handle_command(), interactive_loop(), print_banner(), Any (+35 more)

### Community 11 - "models.py"
Cohesion: 0.15
Nodes (19): BusinessRuleValidationError, _optional_term(), _optional_text(), Collection, Enum, ValueError, Developer-owned semantic catalog models and validation., Base class for invalid semantic metadata. (+11 more)

### Community 14 - "ContextBuilder"
Cohesion: 0.09
Nodes (30): format_type(), Render physical type metadata for prompt serialization., ContextBuilder, ContextBuilderOptions, _quote(), _quoted_table(), Deterministic, capability-rich LLM context construction., Build compact semantic context from a ResolvedQuerySpace or ProfiledQuerySpace. (+22 more)

### Community 15 - "QuerySpaceValidationError"
Cohesion: 0.29
Nodes (10): Tests for QuerySpace domain validation and lookup behavior., _table(), test_developer_query_space_allows_partial_relationship_columns(), test_query_space_accepts_multiple_schemas_and_same_short_name(), test_query_space_accepts_relationship_and_rejects_duplicate(), test_query_space_lookup_reports_missing_table(), test_query_space_rejects_empty_and_duplicate_tables(), test_query_space_rejects_relationship_tables_outside_space() (+2 more)

### Community 16 - "CatalogSnapshot"
Cohesion: 0.06
Nodes (57): Catalog-verified, composition-based space for downstream components., ResolvedQuerySpace, assert_denied_query(), FakeLLMClient, Any, Self, Comprehensive Adversarial Security Test Suite for QuerySmith.  Executes 13 hosti, Regression test ensuring CTE alias column renames retain sensitive lineage and g (+49 more)

### Community 17 - "pytest"
Cohesion: 0.12
Nodes (9): Any, Return a clean, serializable dictionary representation of the report., Alias for to_dict() for Pydantic / standard model compatibility., Return JSON string representation., AuthorizationErrorCode, Any, Enum, str (+1 more)

### Community 18 - "FakeClient"
Cohesion: 0.17
Nodes (21): ColumnOperation, MultipleStatementError, ParsedSQL, Enum, str, AST-based T-SQL parsing and QuerySpace authorization., Security-relevant operation performed on a physical column., One parsed, read-only T-SQL query. (+13 more)

### Community 19 - "TableRef"
Cohesion: 0.05
Nodes (67): AmbiguousPolicyTargetError, ConflictingMandatoryFilterError, InvalidRuntimeContextValueError, OuterJoinRewriteError, Raised when a runtime context value is invalid or unsafe., Raised when a user predicate conflicts with a mandatory row-level policy., Raised when an outer join cannot be safely rewritten with row policy., Raised when a policy target table or alias is ambiguous in AST rewriting. (+59 more)

### Community 20 - "generate_query_in_space"
Cohesion: 0.18
Nodes (11): 10. Verified developer code examples, Backward-compatible v0.1-style generation, Custom deny-by-default QuerySpace, Explicit authorization and execution, Independent column restrictions, Mandatory runtime row policy, Minimal schema-compatible generation, Multi-schema QuerySpace and relationship (+3 more)

### Community 21 - "ask"
Cohesion: 0.17
Nodes (20): normalize_type(), NormalizedType, Physical SQL Server catalog metadata and type normalization., Conservatively compare declared metadata with physical metadata., Require matching normalized physical types for relationship endpoints., Canonical developer/catalog type declaration., Normalize SQL Server base names and optional size parameters., relationship_types_compatible() (+12 more)

### Community 22 - "FakeResult"
Cohesion: 0.14
Nodes (16): CatalogTable, One discovered physical table and all of its columns., Column, MandatoryFilterPolicy, Original SQL Server column model retained for backward compatibility., A typed predicate that must be injected for each matching table scope., Raised when a requested physical table does not exist., TableNotFoundError (+8 more)

### Community 23 - "SQLServerIntrospector"
Cohesion: 0.16
Nodes (16): AuthorizationReport, ColumnUsage, Physical column and all operations observed across the query AST., A strict relationship matched by an equality join., Immutable audit metadata from one authorization pass., RelationshipUsage, FinalAuthorizationError, FinalSQLValidationError (+8 more)

### Community 24 - "ExecutionPolicy"
Cohesion: 0.29
Nodes (6): [0.2.0] - 2026-08-08, Added, Changed, Changelog, Compatibility, Security

### Community 25 - ".resolve"
Cohesion: 0.25
Nodes (8): 7. Important v0.2.0 features in problem/how/benefit/example/proof form, Feature: access profiles and result policy, Feature: deterministic SQL authorization, Feature: execution boundary and auditability, Feature: mandatory row-policy injection, Feature: per-operation column capabilities, Feature: selective, multi-schema QuerySpace, Feature: semantic context separated from physical identifiers

### Community 26 - "SanitizedResult"
Cohesion: 0.20
Nodes (20): _authorize(), Security tests for AST parsing and QuerySpace authorization., _space(), test_aggregate_functions_require_aggregatable_columns(), test_ambiguity_is_fail_closed_and_order_alias_resolves_lineage(), test_column_capabilities_are_operation_specific(), test_correlated_subquery_requires_the_strict_relationship(), test_cte_and_derived_aliases_do_not_bypass_column_access() (+12 more)

### Community 27 - "ExecutionSafetyError"
Cohesion: 0.13
Nodes (10): MissingRuntimeContextError, Raised when a required runtime context key is missing., Raised when database output columns do not match the authorized AST projection., ResultSchemaMismatchError, FakeConnection, FakeResult, Any, FakeConnection (+2 more)

### Community 28 - "test_multi_schema_query_space_flows_through_serializer_llm_and_guard"
Cohesion: 0.15
Nodes (13): _P, _R, _catalog_length(), _catalog_operation(), inspect_tables(), _pair_predicate(), Any, Engine (+5 more)

### Community 29 - "AccessProfileResolver"
Cohesion: 0.08
Nodes (31): MaskingPolicy, Rules for redacting sensitive column values before result delivery., AccessProfileResolver, Access profile resolution and validation for QuerySmith., Resolves an active AccessProfile against a ResolvedQuerySpace., Any, Database result sanitization, hidden column removal, and masking., Sanitized database result container stripped of hidden columns and redacted sens (+23 more)

### Community 30 - "resolver.py"
Cohesion: 0.13
Nodes (53): Exception, ColumnSpec, QuerySpace, Lightweight developer declaration for one physical column., Developer declaration or resolved metadata for one physical table., Immutable developer intent; catalog resolution is still required., TableSpec, CatalogResolver (+45 more)

### Community 31 - "QuerySpaceValidationError"
Cohesion: 0.14
Nodes (8): LLMClient, Protocol, Minimal client protocol used by SQL generation., Return a model completion for the provided prompt., AccessProfile, A named security profile defining host-application access levels., generate_query_in_space(), Generate SQL using only metadata and tables in a QuerySpace or ProfiledQuerySpac

### Community 32 - "_validate_space"
Cohesion: 0.08
Nodes (18): KeyError, _get_table(), _identifier_key(), _legacy_resolved_table(), _optional_identifier(), Collection, QuerySpaceLookupError, QuerySpaceValidationError (+10 more)

### Community 33 - "PolicyEngine"
Cohesion: 0.40
Nodes (5): 11. Security story, Layering, Safe trust-boundary statement, Verified guarantees within the implemented application layer, What QuerySmith does not guarantee

### Community 34 - "execute_select"
Cohesion: 0.07
Nodes (49): AccessProfileError, AliasResolutionError, CrossJoinNotAllowedError, ExecutionSafetyError, MaskingPolicyError, MissingAccessProfileError, MissingQuerySpaceError, ProfileConflictError (+41 more)

### Community 35 - "RequiredFilter"
Cohesion: 0.40
Nodes (5): 2. What QuerySmith is, Intended users, Language support, Problem it solves, Product type

### Community 36 - "test_table_full_name_and_schema_fields"
Cohesion: 0.50
Nodes (4): 14. Marketing-safe claims, Claim carefully, Do not claim, Safe to claim

### Community 37 - "18. Developer experience assessment"
Cohesion: 0.50
Nodes (4): 18. Developer experience assessment, Friction and caveats, Quick video-friendly developer experience, Strengths

### Community 38 - "SpyConnection"
Cohesion: 0.50
Nodes (4): 23. Ranked stories, Best story by format, Top five strongest additions in v0.2.0, Top five strongest things about QuerySmith overall

### Community 39 - "AuthorizedQuery"
Cohesion: 0.50
Nodes (4): 5. v0.1.0 baseline, v0.1.0 architecture and API, v0.1.0 security boundary and limitations, What v0.1.0 could do

### Community 40 - "SemanticTableSpec"
Cohesion: 0.23
Nodes (9): get_field_column_name(), map_django_field_to_sql_type(), parse_db_table(), Any, Django ORM Model Adapter for QuerySmith.  Provides automatic conversion of Djang, Parse a Django db_table string into a schema-qualified TableRef.      Handles ta, Get physical database column name for a Django field., Map Django field class to SQL database type string. (+1 more)

### Community 41 - "FakeConnection"
Cohesion: 0.67
Nodes (3): 16. Visual assets in the repository, Ready to show, Would need a created visual

### Community 42 - "_identifier_key"
Cohesion: 0.18
Nodes (10): Join, Query, Authorize tables, columns, operations, wildcards, and joins from an AST., Raised when a physical source is outside the active QuerySpace., SQLAuthorizer, UnauthorizedTableError, ProfiledQuerySpace, Immutable resolved QuerySpace scoped exclusively to an active AccessProfile. (+2 more)

### Community 43 - "AccessProfileError"
Cohesion: 0.10
Nodes (30): build_query_space(), main(), Initialize engine, resolve QuerySpace against physical database, and launch inte, Build the official QuerySpace for UPM (User Management) and Cor (Core municipal), CatalogColumn, Physical metadata read from ``sys.columns`` and ``sys.types``., django_models_to_query_space(), Convert a sequence of Django model classes into a QuerySmith QuerySpace. (+22 more)

### Community 44 - "test_llm.py"
Cohesion: 0.20
Nodes (16): build_sql_prompt(), generate_sql(), Build the SQL Server query-generation prompt., Generate and validate a safe SQL Server SELECT query., FakeClient, Tests for language model SQL generation., test_build_sql_prompt_explains_semantics_capabilities_and_wildcards(), test_build_sql_prompt_includes_schema_text() (+8 more)

### Community 45 - "ask"
Cohesion: 0.20
Nodes (15): generate_request_id(), Generate a secure unique request identifier., ask(), authorize_query_in_space(), execute_authorized_query(), Engine, Orchestration helpers for QuerySmith query generation and execution., Execute only a final AuthorizedQuery under its resolved execution policy and ret (+7 more)

### Community 46 - "llm.py"
Cohesion: 0.17
Nodes (10): LangChain OpenAI, OpenAI, pyodbc, python-dotenv, requirements, Backward-compatible façade over AST-based SQL authorization., _clean_sql_response(), _first_env_value() (+2 more)

### Community 47 - "ColumnAccess"
Cohesion: 0.20
Nodes (7): ColumnAccess, ColumnAccessLevel, str, Output exposure policy for a column in a query result set., Profile-specific access control settings for a column., Whether a physical column is available to generated SQL or policies., ResultAccess

### Community 48 - "DjangoCatalogIntrospector"
Cohesion: 0.42
Nodes (9): DjangoCatalogIntrospector, Introspector to deliver physical metadata snapshots from Django Model classes., Meta, Tests for QuerySmith Django ORM Adapter., SampleCity, SamplePerson, SampleProvince, test_django_catalog_introspector() (+1 more)

### Community 49 - "generate_query"
Cohesion: 0.31
Nodes (9): introspect_schema(), Compatibility adapter returning the original mutable schema models., generate_query(), Generate safe SQL, retaining the original schema-based adapter., MonkeyPatch, test_generate_query_does_not_execute_sql(), test_generate_query_does_not_instantiate_openai_client(), test_generate_query_passes_serialized_schema_to_llm() (+1 more)

### Community 50 - "pytest"
Cohesion: 0.29
Nodes (7): pytest, MonkeyPatch, Tests for QuerySmith configuration loading., The documented DB_HOST-style variables should load correctly., The DB_TRUSTED_CONNECTION flag should parse common true values., test_config_parses_trusted_flag(), test_config_supports_env_example_names()

### Community 51 - "AuditLogger"
Cohesion: 0.40
Nodes (4): AuditLogger, Protocol, Protocol interface for audit logging backends., Emit one audit event.

## Knowledge Gaps
- **64 isolated node(s):** `querysmith`, `Added`, `Changed`, `Compatibility`, `Security` (+59 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ResolvedQuerySpace` connect `CatalogSnapshot` to `Configuration Management`, `Query Execution and Generation`, `SQL Safety Validation`, `OpenAI Integration`, `Safe SQL Generation`, `TableRef`, `FakeConnection`, `models.py`, `ContextBuilder`, `FakeClient`, `TableRef`, `ask`, `FakeResult`, `SQLServerIntrospector`, `SanitizedResult`, `ExecutionSafetyError`, `AccessProfileResolver`, `resolver.py`, `QuerySpaceValidationError`, `_validate_space`, `execute_select`, `_identifier_key`, `AccessProfileError`, `ask`, `generate_query`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Why does `TableRef` connect `TableRef` to `Configuration Management`, `Query Execution and Generation`, `SQL Safety Validation`, `OpenAI Integration`, `Safe SQL Generation`, `FakeConnection`, `models.py`, `ContextBuilder`, `QuerySpaceValidationError`, `CatalogSnapshot`, `FakeClient`, `TableRef`, `ask`, `FakeResult`, `SQLServerIntrospector`, `SanitizedResult`, `ExecutionSafetyError`, `test_multi_schema_query_space_flows_through_serializer_llm_and_guard`, `AccessProfileResolver`, `resolver.py`, `_validate_space`, `SemanticTableSpec`, `_identifier_key`, `AccessProfileError`, `ColumnAccess`, `DjangoCatalogIntrospector`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Why does `ResolvedColumn` connect `Query Execution and Generation` to `_validate_space`, `OpenAI Integration`, `SemanticTableSpec`, `FakeConnection`, `_identifier_key`, `AccessProfileError`, `models.py`, `ask`, `ContextBuilder`, `ColumnAccess`, `FakeClient`, `ask`, `FakeResult`, `SQLServerIntrospector`, `resolver.py`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Are the 102 inferred relationships involving `TableRef` (e.g. with `build_query_space()` and `AmbiguousColumnError`) actually correct?**
  _`TableRef` has 102 INFERRED edges - model-reasoned connections that need verification._
- **Are the 69 inferred relationships involving `ResolvedQuerySpace` (e.g. with `AmbiguousColumnError` and `AuthorizationReport`) actually correct?**
  _`ResolvedQuerySpace` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 95 inferred relationships involving `TableSpec` (e.g. with `build_query_space()` and `django_models_to_query_space()`) actually correct?**
  _`TableSpec` has 95 INFERRED edges - model-reasoned connections that need verification._
- **Are the 74 inferred relationships involving `QuerySpace` (e.g. with `DjangoCatalogIntrospector` and `introspect_query_space()`) actually correct?**
  _`QuerySpace` has 74 INFERRED edges - model-reasoned connections that need verification._