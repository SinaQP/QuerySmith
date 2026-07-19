# Graph Report - QuerySmith  (2026-07-19)

## Corpus Check
- 19 files · ~3,571 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 189 nodes · 377 edges · 15 communities (10 shown, 5 thin omitted)
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 108 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `fde37039`
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
- OpenAI Client Compatibility
- Fake Chat Components
- OpenAI Client Testing
- load_config
- OpenAI Embeddings
- QuerySmith Core
- QuerySmith Framework
- .get_model

## God Nodes (most connected - your core abstractions)
1. `UnsafeQueryError` - 28 edges
2. `validate_safe_select()` - 20 edges
3. `OpenAICompatibleClient` - 20 edges
4. `Table` - 17 edges
5. `FakeEngine` - 15 edges
6. `generate_sql()` - 13 edges
7. `Column` - 13 edges
8. `generate_query()` - 11 edges
9. `serialize_schema()` - 10 edges
10. `FakeClient` - 10 edges

## Surprising Connections (you probably didn't know these)
- `FakeChat` --uses--> `UnsafeQueryError`  [INFERRED]
  tests/test_llm.py → src/querysmith/guard.py
- `FakeChoice` --uses--> `UnsafeQueryError`  [INFERRED]
  tests/test_llm.py → src/querysmith/guard.py
- `FakeClient` --uses--> `UnsafeQueryError`  [INFERRED]
  tests/test_llm.py → src/querysmith/guard.py
- `FakeCompletion` --uses--> `UnsafeQueryError`  [INFERRED]
  tests/test_llm.py → src/querysmith/guard.py
- `FakeCompletions` --uses--> `UnsafeQueryError`  [INFERRED]
  tests/test_llm.py → src/querysmith/guard.py

## Import Cycles
- None detected.

## Communities (15 total, 5 thin omitted)

### Community 0 - "Configuration Management"
Cohesion: 0.12
Nodes (21): main(), Run a small local QuerySmith prototype., DBConfig, Configuration loading for QuerySmith., SQL Server connection configuration., build_url(), make_engine(), Engine (+13 more)

### Community 1 - "Database Schema Metadata"
Cohesion: 0.13
Nodes (24): introspect_schema(), Engine, Read table, column, primary key, and foreign key metadata for a schema., Column, ForeignKey, Schema data models for QuerySmith., A SQL Server foreign key relationship., A SQL Server table with columns and foreign keys. (+16 more)

### Community 2 - "Query Execution and Generation"
Cohesion: 0.13
Nodes (19): execute_select(), generate_query(), Engine, Generate a safe SQL query from a question and database schema., Validate and execute a SELECT query with a conservative row limit., FakeClient, FakeConnection, FakeEngine (+11 more)

### Community 3 - "SQL Safety Validation"
Cohesion: 0.19
Nodes (21): _normalize_sql(), Application-level validation for generated SQL Server SELECT queries., Validate that SQL text is a single conservative read-only SELECT query.      Ret, Raised when SQL text does not pass the read-only safety guard., _remove_optional_trailing_semicolon(), UnsafeQueryError, validate_safe_select(), Tests for SQL safety guardrails. (+13 more)

### Community 4 - "OpenAI Integration"
Cohesion: 0.12
Nodes (14): LangChain OpenAI, OpenAI, Protocol, pyodbc, python-dotenv, requirements, SQLAlchemy, SQL Server schema introspection. (+6 more)

### Community 5 - "SQL Prompt Building"
Cohesion: 0.24
Nodes (10): build_sql_prompt(), Build the SQL Server query-generation prompt., FakeChoice, FakeCompletion, FakeMessage, Tests for language model SQL generation., test_build_sql_prompt_includes_schema_text(), test_build_sql_prompt_includes_user_question() (+2 more)

### Community 6 - "Safe SQL Generation"
Cohesion: 0.25
Nodes (10): _clean_sql_response(), generate_sql(), Generate and validate a safe SQL Server SELECT query., Strip whitespace and remove one surrounding markdown SQL fence., FakeClient, test_generate_sql_raises_for_delete(), test_generate_sql_raises_for_multiple_statements(), test_generate_sql_removes_markdown_sql_fences() (+2 more)

### Community 7 - "OpenAI Client Compatibility"
Cohesion: 0.27
Nodes (9): OpenAICompatibleClient, OpenAI-compatible client with AvalAI defaults., Return a chat completion for the prompt., MonkeyPatch, test_openai_compatible_client_accepts_explicit_config(), test_openai_compatible_client_default_base_url(), test_openai_compatible_client_env_vars_override_defaults(), test_openai_compatible_client_explicit_args_override_env_vars() (+1 more)

### Community 9 - "OpenAI Client Testing"
Cohesion: 0.67
Nodes (3): FakeOpenAIChatClient, test_openai_compatible_client_complete_rejects_empty_response(), test_openai_compatible_client_complete_uses_internal_client()

### Community 10 - "load_config"
Cohesion: 0.18
Nodes (12): pytest, load_config(), _parse_bool(), Parse a permissive boolean environment value., Load database configuration from environment variables., MonkeyPatch, Tests for QuerySmith configuration loading., The documented DB_HOST-style variables should load correctly. (+4 more)

## Knowledge Gaps
- **4 isolated node(s):** `querysmith`, `QuerySmith`, `pyodbc`, `python-dotenv`
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UnsafeQueryError` connect `SQL Safety Validation` to `Query Execution and Generation`, `SQL Prompt Building`, `Safe SQL Generation`, `Fake Chat Components`, `OpenAI Client Testing`, `load_config`?**
  _High betweenness centrality (0.230) - this node is a cross-community bridge._
- **Why does `OpenAICompatibleClient` connect `OpenAI Client Compatibility` to `OpenAI Integration`, `SQL Prompt Building`, `Safe SQL Generation`, `Fake Chat Components`, `OpenAI Client Testing`, `OpenAI Embeddings`, `.get_model`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Why does `Table` connect `Database Schema Metadata` to `Query Execution and Generation`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `UnsafeQueryError` (e.g. with `test_reject_block_comments()` and `test_reject_dangerous_write_keywords()`) actually correct?**
  _`UnsafeQueryError` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `validate_safe_select()` (e.g. with `generate_sql()` and `execute_select()`) actually correct?**
  _`validate_safe_select()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `OpenAICompatibleClient` (e.g. with `FakeChat` and `FakeChoice`) actually correct?**
  _`OpenAICompatibleClient` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Table` (e.g. with `test_table_full_name_and_schema_fields()` and `FakeClient`) actually correct?**
  _`Table` has 9 INFERRED edges - model-reasoned connections that need verification._