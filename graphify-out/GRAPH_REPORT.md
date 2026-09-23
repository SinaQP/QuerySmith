# Graph Report - QuerySmith  (2026-08-08)

## Corpus Check
- 46 files · ~53,100 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1211 nodes · 4919 edges · 51 communities (45 shown, 6 thin omitted)
- Extraction: 50% EXTRACTED · 50% INFERRED · 0% AMBIGUOUS · INFERRED: 2447 edges (avg confidence: 0.59)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `39eabb8a`
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
- CapturingClient

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

## Communities (51 total, 6 thin omitted)

### Community 0 - "Configuration Management"
Cohesion: 0.14
Nodes (25): execute_select(), Validate and execute a SELECT query with a conservative row limit., FakeCatalogIntrospector, FakeClient, FakeEngine, _mandatory_policy_space(), FakeConnection, Tests for QuerySmith pipeline helpers. (+17 more)

### Community 1 - "Database Schema Metadata"
Cohesion: 0.10
Nodes (19): 12. Differentiators from `prompt = schema + question; db.execute(llm(prompt))`, 13. Target audiences and best demonstrations, 15. Raw factual hook concepts (not scripts), 17. Installation and project metadata, 19. Test-derived capabilities and edge cases, 1. Executive source of truth, 20. Documentation and release drift, 21. Conceptual alternatives and where QuerySmith fits (+11 more)

### Community 2 - "Query Execution and Generation"
Cohesion: 0.12
Nodes (9): Join, Collection, Expression, Query, Scope, Authorize tables, columns, operations, wildcards, and joins from an AST., SQLAuthorizer, Composition of immutable physical, semantic, and capability metadata. (+1 more)

### Community 3 - "SQL Safety Validation"
Cohesion: 0.15
Nodes (27): Parse one read-only T-SQL query and optionally authorize its QuerySpace use., validate_safe_select(), _capability_space(), _query_space(), Tests for SQL safety guardrails., test_accept_select_with_trailing_semicolon(), test_accept_simple_select(), test_accept_with_cte_select() (+19 more)

### Community 4 - "OpenAI Integration"
Cohesion: 0.10
Nodes (55): KeyError, AliasConflictError, CatalogResolutionError, ColumnNotFoundError, ColumnTypeMismatchError, DefaultColumnPolicy, FilterOperator, ForbiddenColumnError (+47 more)

### Community 5 - "SQL Prompt Building"
Cohesion: 0.07
Nodes (42): ChatOpenAI, OpenAIEmbeddings, Backward-compatible façade over AST-based SQL authorization., build_sql_prompt(), _clean_sql_response(), _first_env_value(), generate_sql(), OpenAICompatibleClient (+34 more)

### Community 6 - "Safe SQL Generation"
Cohesion: 0.18
Nodes (9): FakeEngine, FakeConnection, FakeEngine, Self, Tests for bounded exact-table SQL Server introspection., test_inspect_tables_uses_three_bounded_parameterized_queries(), test_selected_introspection_returns_resolved_space_and_catalog_fk(), test_selective_introspection_caps_batch_below_sql_server_parameter_limit() (+1 more)

### Community 8 - "_validate_space"
Cohesion: 0.11
Nodes (18): Logger, AuditEvent, AuditLogger, AuditLoggingPolicy, NullAuditLogger, Any, Protocol, PythonLoggingAuditLogger (+10 more)

### Community 9 - "FakeConnection"
Cohesion: 0.14
Nodes (59): AmbiguousColumnError, AuthorizationReport, _Binding, ColumnOperation, ColumnUsage, MultipleStatementError, ParsedSQL, Enum (+51 more)

### Community 10 - "test_multi_schema_query_space_flows_through_serializer_llm_and_guard"
Cohesion: 0.05
Nodes (53): build_engine(), build_llm_client(), DemoState, format_terminal_table(), handle_command(), interactive_loop(), main(), print_banner() (+45 more)

### Community 11 - "models.py"
Cohesion: 0.23
Nodes (13): _optional_term(), _optional_text(), Collection, Enum, ValueError, Developer-owned semantic catalog models and validation., Base class for invalid semantic metadata., RuleEnforcement (+5 more)

### Community 14 - "ContextBuilder"
Cohesion: 0.14
Nodes (18): format_type(), Render physical type metadata for prompt serialization., ContextBuilder, ContextBuilderOptions, _quote(), _quoted_table(), Deterministic, capability-rich LLM context construction., Build compact semantic context from a ResolvedQuerySpace or ProfiledQuerySpace. (+10 more)

### Community 15 - "QuerySpaceValidationError"
Cohesion: 0.13
Nodes (15): QuerySpaceValidationError, Raised when QuerySpace metadata is internally inconsistent., _validated_identifier(), Tests for QuerySpace domain validation and lookup behavior., _table(), test_developer_query_space_allows_partial_relationship_columns(), test_execution_policy_rejects_invalid_limits(), test_query_space_accepts_multiple_schemas_and_same_short_name() (+7 more)

### Community 16 - "CatalogSnapshot"
Cohesion: 0.06
Nodes (56): Catalog-verified, composition-based space for downstream components., ResolvedQuerySpace, assert_denied_query(), FakeLLMClient, Any, Comprehensive Adversarial Security Test Suite for QuerySmith.  Executes 13 hosti, Regression test ensuring CTE alias column renames retain sensitive lineage and g, test_attack_scenario_10_missing_runtime_tenant() (+48 more)

### Community 17 - "pytest"
Cohesion: 0.12
Nodes (9): Any, Return a clean, serializable dictionary representation of the report., Alias for to_dict() for Pydantic / standard model compatibility., Return JSON string representation., AuthorizationErrorCode, Any, Enum, str (+1 more)

### Community 18 - "FakeClient"
Cohesion: 0.21
Nodes (9): OuterJoinRewriteError, Raised when an outer join cannot be safely rewritten with row policy., MandatoryFilterPolicy, A typed predicate that must be injected for each matching table scope., PolicyInjector, Expression, Query, Scope (+1 more)

### Community 19 - "TableRef"
Cohesion: 0.16
Nodes (21): _make_orders_space(), Comprehensive unit and security integration tests for Row-Level Access Policies,, test_contradictory_user_predicate_is_null_raises_error(), test_contradictory_user_predicate_literal_mismatch_raises_error(), test_contradictory_user_predicate_neq_raises_error(), test_cte_and_subquery_scopes_receive_policies(), test_execution_boundary_only_accepts_authorized_query(), test_existing_where_merged_with_and_precedence() (+13 more)

### Community 20 - "generate_query_in_space"
Cohesion: 0.18
Nodes (11): 10. Verified developer code examples, Backward-compatible v0.1-style generation, Custom deny-by-default QuerySpace, Explicit authorization and execution, Independent column restrictions, Mandatory runtime row policy, Minimal schema-compatible generation, Multi-schema QuerySpace and relationship (+3 more)

### Community 21 - "ask"
Cohesion: 0.11
Nodes (24): normalize_type(), NormalizedType, Physical SQL Server catalog metadata and type normalization., Conservatively compare declared metadata with physical metadata., Require matching normalized physical types for relationship endpoints., Canonical developer/catalog type declaration., Normalize SQL Server base names and optional size parameters., relationship_types_compatible() (+16 more)

### Community 22 - "FakeResult"
Cohesion: 0.15
Nodes (19): Column, _legacy_foreign_key_target(), Original SQL Server column model retained for backward compatibility., Original mutable table model retained for backward compatibility., Table, _qualified_referenced_table(), _qualified_table_name(), Serialize schema metadata for prompt context. (+11 more)

### Community 23 - "SQLServerIntrospector"
Cohesion: 0.18
Nodes (8): AmbiguousPolicyTargetError, FinalSQLValidationError, Raised when a policy target table or alias is ambiguous in AST rewriting., Raised when rewritten SQL fails final authorization or re-parsing., AuthorizedQuery, InjectionResult, Immutable final SQL and audit metadata safe for the execution boundary., Internal immutable result of AST policy injection.

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
Cohesion: 0.15
Nodes (11): ConflictingMandatoryFilterError, MissingRuntimeContextError, Raised when a required runtime context key is missing., Raised when a user predicate conflicts with a mandatory row-level policy., FakeConnection, FakeEngine, FakeResult, Any (+3 more)

### Community 28 - "test_multi_schema_query_space_flows_through_serializer_llm_and_guard"
Cohesion: 0.15
Nodes (13): _P, _R, _catalog_length(), _catalog_operation(), introspect_query_space(), _pair_predicate(), Any, Bounded, parameterized SQL Server catalog introspection. (+5 more)

### Community 29 - "AccessProfileResolver"
Cohesion: 0.06
Nodes (43): MaskingPolicy, Rules for redacting sensitive column values before result delivery., authorize_query_in_space(), Pre-validate runtime context values and required keys before triggering LLM gene, Generate SQL and return only the final, policy-applied authorization result., _validate_runtime_context_before_llm(), AccessProfileResolver, Access profile resolution and validation for QuerySmith. (+35 more)

### Community 30 - "resolver.py"
Cohesion: 0.12
Nodes (56): Exception, ColumnSpec, ExecutionPolicy, QuerySpace, Lightweight developer declaration for one physical column., Developer declaration or resolved metadata for one physical table., Execution limits enforced for SQL generated inside a QuerySpace., Immutable developer intent; catalog resolution is still required. (+48 more)

### Community 31 - "QuerySpaceValidationError"
Cohesion: 0.19
Nodes (13): LLMClient, Protocol, Minimal client protocol used by SQL generation., Return a model completion for the provided prompt., generate_query(), generate_query_in_space(), Generate safe SQL, retaining the original schema-based adapter., Generate SQL using only metadata and tables in a QuerySpace or ProfiledQuerySpac (+5 more)

### Community 32 - "_validate_space"
Cohesion: 0.17
Nodes (5): _get_table(), _identifier_key(), Collection, Match the case-insensitive identifier behavior used by SQL Server., _validate_space()

### Community 33 - "PolicyEngine"
Cohesion: 0.40
Nodes (5): 11. Security story, Layering, Safe trust-boundary statement, Verified guarantees within the implemented application layer, What QuerySmith does not guarantee

### Community 34 - "execute_select"
Cohesion: 0.06
Nodes (69): ColumnOperationNotAllowedError, Raised when a column is used for a denied SQL operation., Raised when a column is absent, denied, or policy-only., UnauthorizedColumnError, AccessProfileError, AliasResolutionError, CrossJoinNotAllowedError, ExecutionSafetyError (+61 more)

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
Cohesion: 0.32
Nodes (5): get_field_column_name(), map_django_field_to_sql_type(), Any, Get physical database column name for a Django field., Map Django field class to SQL database type string.

### Community 41 - "FakeConnection"
Cohesion: 0.67
Nodes (3): 16. Visual assets in the repository, Ready to show, Would need a created visual

### Community 42 - "_identifier_key"
Cohesion: 0.26
Nodes (18): PolicyEngine, Authorize, inject typed policies, and re-authorize final SQL., _policy_space(), Mandatory policy injection, re-authorization, and audit tests., test_existing_equivalent_mandatory_literal_is_not_duplicated(), test_existing_where_or_precedence_is_preserved(), test_final_authorization_does_not_trust_policy_column_in_projection(), test_final_authorization_rejects_a_malicious_injector() (+10 more)

### Community 43 - "AccessProfileError"
Cohesion: 0.07
Nodes (26): build_query_space(), Build the official QuerySpace for UPM (User Management) and Cor (Core municipal), CatalogColumn, CatalogSnapshot, CatalogTable, Physical metadata read from ``sys.columns`` and ``sys.types``., One discovered physical table and all of its columns., Bounded catalog result for an exact set of requested tables. (+18 more)

### Community 44 - "test_llm.py"
Cohesion: 0.27
Nodes (11): InvalidRuntimeContextValueError, Raised when a runtime context value is invalid or unsafe., Mandatory policy injection and final SQL authorization orchestration., Pre-validate runtime context keys and values against active row policies., _validate_context_value(), validate_runtime_context(), test_context_rejects_callable_or_sql_objects(), test_in_operator_rejects_empty_collection() (+3 more)

### Community 45 - "ask"
Cohesion: 0.14
Nodes (19): generate_request_id(), Generate a secure unique request identifier., inspect_tables(), introspect_schema(), Engine, Typed convenience API for exact-table catalog introspection., Compatibility adapter returning the original mutable schema models., Read metadata for exact table identities in a bounded query count. (+11 more)

### Community 47 - "ColumnAccess"
Cohesion: 0.17
Nodes (9): ProfileConflictError, Raised when access profile rules or capabilities are internally conflicting., ColumnAccess, ProfiledQuerySpace, str, Output exposure policy for a column in a query result set., Immutable resolved QuerySpace scoped exclusively to an active AccessProfile., Profile-specific access control settings for a column. (+1 more)

### Community 48 - "DjangoCatalogIntrospector"
Cohesion: 0.25
Nodes (13): DjangoCatalogIntrospector, parse_db_table(), Django ORM Model Adapter for QuerySmith.  Provides automatic conversion of Djang, Introspector to deliver physical metadata snapshots from Django Model classes., Parse a Django db_table string into a schema-qualified TableRef.      Handles ta, Meta, Tests for QuerySmith Django ORM Adapter., SampleCity (+5 more)

## Knowledge Gaps
- **62 isolated node(s):** `Added`, `Changed`, `Compatibility`, `Security`, `1. Executive source of truth` (+57 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ResolvedQuerySpace` connect `CatalogSnapshot` to `Configuration Management`, `Query Execution and Generation`, `SQL Safety Validation`, `OpenAI Integration`, `Safe SQL Generation`, `TableRef`, `FakeConnection`, `ContextBuilder`, `FakeClient`, `TableRef`, `ask`, `FakeResult`, `SQLServerIntrospector`, `SanitizedResult`, `ExecutionSafetyError`, `test_multi_schema_query_space_flows_through_serializer_llm_and_guard`, `AccessProfileResolver`, `resolver.py`, `QuerySpaceValidationError`, `_validate_space`, `execute_select`, `_identifier_key`, `AccessProfileError`, `test_llm.py`, `ask`, `llm.py`, `ColumnAccess`, `generate_query`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Why does `TableRef` connect `TableRef` to `Configuration Management`, `Query Execution and Generation`, `SQL Safety Validation`, `OpenAI Integration`, `Safe SQL Generation`, `FakeConnection`, `models.py`, `ContextBuilder`, `QuerySpaceValidationError`, `CatalogSnapshot`, `FakeClient`, `ask`, `FakeResult`, `SQLServerIntrospector`, `SanitizedResult`, `ExecutionSafetyError`, `test_multi_schema_query_space_flows_through_serializer_llm_and_guard`, `AccessProfileResolver`, `resolver.py`, `_validate_space`, `execute_select`, `_identifier_key`, `AccessProfileError`, `ask`, `ColumnAccess`, `DjangoCatalogIntrospector`, `generate_query`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `CatalogColumn` connect `AccessProfileError` to `Configuration Management`, `Query Execution and Generation`, `OpenAI Integration`, `TableRef`, `FakeConnection`, `test_multi_schema_query_space_flows_through_serializer_llm_and_guard`, `QuerySpaceValidationError`, `CatalogSnapshot`, `FakeClient`, `ask`, `FakeResult`, `test_multi_schema_query_space_flows_through_serializer_llm_and_guard`, `AccessProfileResolver`, `resolver.py`, `execute_select`, `SemanticTableSpec`, `ask`, `llm.py`, `ColumnAccess`, `DjangoCatalogIntrospector`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Are the 102 inferred relationships involving `TableRef` (e.g. with `build_query_space()` and `AmbiguousColumnError`) actually correct?**
  _`TableRef` has 102 INFERRED edges - model-reasoned connections that need verification._
- **Are the 69 inferred relationships involving `ResolvedQuerySpace` (e.g. with `AmbiguousColumnError` and `AuthorizationReport`) actually correct?**
  _`ResolvedQuerySpace` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 95 inferred relationships involving `TableSpec` (e.g. with `build_query_space()` and `django_models_to_query_space()`) actually correct?**
  _`TableSpec` has 95 INFERRED edges - model-reasoned connections that need verification._
- **Are the 74 inferred relationships involving `QuerySpace` (e.g. with `DjangoCatalogIntrospector` and `introspect_query_space()`) actually correct?**
  _`QuerySpace` has 74 INFERRED edges - model-reasoned connections that need verification._