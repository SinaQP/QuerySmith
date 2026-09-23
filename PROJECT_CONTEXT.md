# QuerySmith project context

This document is a working map of the repository at commit `39eabb8` (reviewed 2026-09-23). Source code is authoritative if this document and code diverge. Do not put database credentials, API keys, or customer data in this file.

## Purpose and scope

QuerySmith is a Python 3.11+ library (package version `0.2.0`) for turning Persian or English natural-language questions into Microsoft SQL Server T-SQL `SELECT` queries. It can return authorized SQL or execute it and return sanitized rows. It uses SQLAlchemy/pyodbc for SQL Server, sqlglot for parsing and rewriting SQL, and an OpenAI-compatible LLM client (AvalAI defaults). The library is intended to be embedded in a host application; `main.py` is an interactive real-database demonstration, not the package entry point.

The security boundary is a developer-defined `QuerySpace`, resolved against the physical catalog, then narrowed by an access profile and execution policy. LLM output is untrusted. QuerySmith parses, authorizes, rewrites, and re-authorizes it before an `AuthorizedQuery` can cross the execution boundary. Deployments still need a least-privilege, read-only SQL Server account and their own authentication and resource controls.

## Repository map

| Path | Responsibility |
| --- | --- |
| `src/querysmith/__init__.py` | Public package exports and version. |
| `src/querysmith/models.py` | Immutable QuerySpace, table/column/relationship, access profile, filter, execution-policy, and resolved-domain models. |
| `src/querysmith/catalog.py` | Physical SQL Server catalog snapshot and type normalization/compatibility. |
| `src/querysmith/introspector.py` | SQL Server catalog introspection, including selected-table introspection. |
| `src/querysmith/resolver.py` | Compose developer declarations, catalog facts, and semantic metadata into a `ResolvedQuerySpace`; validate identities, types, relationships, and rules. |
| `src/querysmith/semantic.py` | Semantic names, descriptions, capabilities, sensitivity, examples, and business-rule models. |
| `src/querysmith/profiles.py` | Resolve a named `AccessProfile` to effective table/column permissions, result visibility, masks, and required filters. |
| `src/querysmith/context.py` | Build the profile-aware schema and semantic context sent to the LLM. |
| `src/querysmith/serializer.py` | Schema serialization, including compatibility paths. |
| `src/querysmith/llm.py` | `LLMClient` protocol, OpenAI-compatible implementation, prompt construction, response cleanup, and initial SQL guard. |
| `src/querysmith/authorization.py` | sqlglot T-SQL parser, AST-based table/column/operation/join authorization, projection lineage, and authorization report. |
| `src/querysmith/guard.py` | Compatibility-facing `validate_safe_select` wrapper. |
| `src/querysmith/policy.py` | Runtime-context validation, mandatory-filter and row-limit AST rewriting, final authorization, and `AuthorizedQuery`. |
| `src/querysmith/sanitizer.py` | Result row cap, output-schema checking, hidden-column removal, and masking. |
| `src/querysmith/pipeline.py` | High-level orchestration: resolve, generate, authorize, optionally execute, audit, and sanitize. |
| `src/querysmith/audit.py` | Structured audit events/loggers and SQL-literal redaction. |
| `src/querysmith/exceptions.py` | Typed policy, execution, rewrite, result, and authorization errors and codes. |
| `src/querysmith/config.py`, `db.py` | Environment-driven SQL Server configuration and SQLAlchemy engine creation. |
| `src/querysmith/django_adapter.py` | Convert Django model metadata to a QuerySpace and introspect via Django connections. |
| `main.py` | Interactive playground with a large example QuerySpace and live database/LLM flow. |
| `tests/` | Unit, adversarial security, Django, pipeline, and SQL Server integration tests. |
| `.github/workflows/` | Tag-triggered PyPI publishing and SQL Server integration CI. |
| `graphify-out/` | Generated knowledge graph and report; the graph was built from commit `39eabb8`. |

## Core data model

- `TableRef` identifies a physical table by schema and name. `TableSpec`, `ColumnSpec`, and `RelationshipSpec` express developer intent.
- `QuerySpace` is the immutable requested scope. Its default column policy is `DENY`. `CatalogResolver` verifies the requested scope against an exact catalog snapshot and returns `ResolvedQuerySpace`.
- `SemanticCatalog` supplies natural-language aliases, descriptions, types, examples, sensitivities, capabilities, and business rules. Semantic names guide the prompt; generated SQL must use physical identifiers.
- `AccessProfileResolver` turns a resolved space plus an active `AccessProfile` into `ProfiledQuerySpace`. Profile-aware spaces require an explicitly declared profile. Table and column permissions, operation capabilities, hidden or masked result access, and required filters become effective here.
- `ExecutionPolicy` defaults to `max_rows=100`, `timeout_seconds=15`, `max_joins=5`, execution enabled, CTEs/subqueries allowed, and inner/left joins allowed. Wildcards, unlisted joins, unqualified tables, and cross joins are disallowed by default. `max_rows` must be 1–1000.
- `RequiredFilter` and `MandatoryFilterPolicy` define enforced predicates. Trusted runtime values are parameterized; the LLM is not responsible for enforcing them.
- `AuthorizedQuery` carries final SQL, bound parameters, applied policies, and a successful authorization report. `SanitizedResult` carries visible columns, sanitized rows, count, truncation status, and profile.

## End-to-end flow

1. The caller supplies exactly one of `schema` or `query_space` to `ask()`. A declared `QuerySpace` is resolved through `CatalogResolver` and `SQLServerIntrospector`; an already resolved space is validated. The schema convenience path introspects that schema.
2. `AccessProfileResolver` computes the effective profile. If execution is requested, the execution policy must permit it.
3. `authorize_query_in_space()` validates required runtime-context keys and value shapes before contacting the LLM. `ContextBuilder` renders only the effective table/column metadata and relationship guidance. `generate_sql()` asks the `LLMClient` for one T-SQL query and performs an initial read-only parse check.
4. `PolicyEngine.authorize_and_apply()` parses and authorizes the generated SQL against the effective space. `PolicyInjector` adds typed mandatory predicates and a T-SQL row limit to a copied AST, with bound parameters. The final SQL is parsed and authorized again; table and physical-column references are checked for unexpected changes.
5. `ask(..., execute=False)` returns the final SQL string. `ask(..., execute=True)` passes the `AuthorizedQuery` to `execute_authorized_query()`, which executes with bound parameters, fetches up to `max_rows + 1`, then applies `ResultSanitizer` to hide/mask outputs and mark truncation.
6. The pipeline emits structured request, profile, generation, authorization, and execution audit events when a logger is supplied. The default logger discards events.

For lower-level use, call `authorize_query_in_space()` and then `execute_authorized_query()`. The compatibility `generate_query()` and `execute_select()` helpers remain; direct execution requires a resolved or profiled scope.

## Security behavior and limits

- `SQLParser` accepts exactly one parsed read-only query and rejects comments, `SELECT INTO`, dangerous functions, table functions/external sources, and system variables. `SQLAuthorizer` checks permitted tables, physical columns, operation capabilities, join relationships, wildcards, and query shape using the AST and scope/lineage information.
- Policy injection is AST-based and parameterized. It handles aliases, joins, CTEs, subqueries, and set operations where safe, and fails closed on unsafe rewrite shapes or contradictory predicates. Final authorization checks the rewritten query.
- Runtime context rejects missing required keys, raw SQL-like objects, callables, complex values, and invalid `IN` collections (including empty collections or more than 1,000 items).
- Result policy can remove hidden columns and apply full, partial, or constant masks. Execution also applies row limits and a configured timeout; use database-side limits and privileges as additional controls.
- This package only supports SQL Server T-SQL `SELECT` queries. SQL correctness and efficiency still depend on question clarity, schema metadata, and model output. The external LLM endpoint is required for generation.

## Public API and setup

The main entry point is `querysmith.ask(question, query_space=..., access_profile=..., runtime_context=..., engine=..., client=..., execute=False)`. Other important exports include `QuerySpace`, `TableSpec`, `ColumnSpec`, `RelationshipSpec`, `ExecutionPolicy`, `AccessProfile`, `CatalogResolver`, `SQLServerIntrospector`, `OpenAICompatibleClient`, `PolicyEngine`, `AuthorizedQuery`, `ResultSanitizer`, `DjangoCatalogIntrospector`, and audit/report types. Check `src/querysmith/__init__.py` for the complete current export list.

Install for development with `python -m pip install -e ".[dev]"`. SQL Server access needs a matching installed Microsoft ODBC driver in addition to `pyodbc`. Database settings come from `DB_SERVER`/`DB_HOST`, `DB_DATABASE`/`DB_NAME`, credentials, driver, and optional trusted-connection variables; see `.env.example` and `src/querysmith/config.py`. The LLM client looks for `QUERYSMITH_LLM_API_KEY`, `AVALAI_API_KEY`, or `OPENAI_API_KEY`; it uses `QUERYSMITH_LLM_BASE_URL` or `AVALAI_BASE_URL` and `QUERYSMITH_LLM_MODEL` when set. The default base URL is AvalAI. Do not copy `.env` values into context or logs.

## Tests, release, and working conventions

- `tests/` has focused model, resolver, context, semantic, authorization, policy, pipeline, sanitizer, audit, Django-adapter, and adversarial-security coverage. `tests/test_sqlserver_integration.py` requires a live SQL Server. Run local unit tests with `python -m pytest -q -m "not integration and not sqlserver"`.
- `docker-compose.integration.yml` and `.env.integration.example` support local SQL Server integration runs. `.github/workflows/integration-sqlserver.yml` runs marked integration tests against a SQL Server 2022 service. `.github/workflows/publish-to-pypi.yml` builds and publishes a distribution on `v*` tags.
- Packaging is configured in `pyproject.toml` with Hatchling; the wheel contains `src/querysmith`. `CHANGELOG.md` documents the 0.2.0 feature/security changes. `README.md` is the usage and limitations guide.
- `AGENTS.md` says to query the existing graph first for codebase questions and to run `graphify update .` after code changes. The separate `agent-rules Agent.md` mentioned in the user-provided instructions was not found in this workspace as of this review.
- At the time this file was written, four generated files under `graphify-out/` were already modified in the working tree. They were not part of this documentation change. The graphify CLI was unavailable on `PATH`; source files and the existing graph report were used for this context.

## Where to start for common changes

| Task | Start with |
| --- | --- |
| Add or change a policy knob | `models.py`, `profiles.py`, `policy.py`, then policy/authorization tests. |
| Change accepted SQL forms | `authorization.py`, `policy.py`, adversarial tests. |
| Change prompt/schema context | `context.py`, `semantic.py`, `llm.py`, context/LLM tests. |
| Add a database metadata source | `introspector.py`, `catalog.py`, `resolver.py`, adapter tests. |
| Change execution or output handling | `pipeline.py`, `sanitizer.py`, pipeline/sanitizer tests. |
| Change public package behavior | `__init__.py`, `README.md`, `CHANGELOG.md`, relevant tests. |

Keep the scope and policies as the authority. Prompt text helps generation, but it is not an authorization boundary.
