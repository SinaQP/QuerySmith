from dotenv import load_dotenv

from querysmith.config import load_config
from querysmith.db import make_engine
from querysmith.llm import OpenAICompatibleClient
from querysmith.pipeline import execute_select, generate_query


QUESTION = "فردی با نام سینا رو پیدا کن"
SCHEMA = "core"
EXECUTE_QUERY = False


def main() -> None:
    """Run a small local QuerySmith prototype."""

    load_dotenv()

    engine = make_engine(load_config())
    client = OpenAICompatibleClient()

    sql = generate_query(
        question=QUESTION,
        engine=engine,
        client=client,
        schema=SCHEMA,
    )

    print("Generated SQL:")
    print(sql)

    if EXECUTE_QUERY:
        rows = execute_select(engine, sql, max_rows=50)
        print("Rows:")
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
