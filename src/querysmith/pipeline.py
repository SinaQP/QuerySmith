"""Orchestration helpers for QuerySmith query generation and execution."""

from sqlalchemy import Engine, text

from querysmith.guard import validate_safe_select
from querysmith.introspector import introspect_schema
from querysmith.llm import LLMClient, generate_sql
from querysmith.serializer import serialize_schema


def generate_query(
    question: str,
    engine: Engine,
    client: LLMClient,
    schema: str = "dbo",
) -> str:
    """Generate a safe SQL query from a question and database schema."""

    tables = introspect_schema(engine, schema=schema)
    schema_text = serialize_schema(tables)
    return generate_sql(question, schema_text, client)


def execute_select(
    engine: Engine,
    sql: str,
    max_rows: int = 100,
) -> list[dict[str, object]]:
    """Validate and execute a SELECT query with a conservative row limit."""

    if (
        not isinstance(max_rows, int)
        or isinstance(max_rows, bool)
        or max_rows <= 0
        or max_rows > 1000
    ):
        raise ValueError("max_rows must be an int between 1 and 1000.")

    safe_sql = validate_safe_select(sql)
    limited_sql = (
        f"SELECT TOP ({max_rows}) *\n"
        "FROM (\n"
        f"{safe_sql}\n"
        ") AS querysmith_subquery"
    )

    with engine.connect() as connection:
        result = connection.execute(text(limited_sql))
        return [dict(row) for row in result.mappings()]
