"""Database connection helpers for QuerySmith."""

from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, text

from querysmith.config import DBConfig


def make_engine(config: DBConfig) -> Engine:
    """Create a SQLAlchemy engine for SQL Server through pyodbc."""

    username = quote_plus(config.username)
    password = quote_plus(config.password)
    driver = quote_plus(config.driver)
    connection_string = (
        f"mssql+pyodbc://{username}:{password}@{config.server}/"
        f"{config.database}?driver={driver}"
    )

    return create_engine(connection_string, pool_pre_ping=True)


def test_connection(engine: Engine) -> str:
    """Return the SQL Server version string for a working connection."""

    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT @@VERSION")).scalar_one()
    except Exception as error:
        raise ConnectionError(
            f"Failed to connect to SQL Server or run version check: {error}"
        ) from error

    return str(version)
