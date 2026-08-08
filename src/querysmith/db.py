"""Database connection helpers for QuerySmith."""

from sqlalchemy import URL, Engine, create_engine, text

from querysmith.config import DBConfig


def build_url(cfg: DBConfig) -> URL:
    """Build a SQLAlchemy URL from a raw ODBC connection string."""

    odbc_parts = [
        f"DRIVER={{{cfg.driver}}}",
        f"SERVER={cfg.server}",
        f"DATABASE={cfg.database}",
        "TrustServerCertificate=yes",
    ]

    if cfg.trusted_connection:
        odbc_parts.append("Trusted_Connection=yes")
    else:
        odbc_parts.extend([f"UID={cfg.username}", f"PWD={cfg.password}"])

    odbc_string = ";".join(odbc_parts) + ";"
    return URL.create("mssql+pyodbc", query={"odbc_connect": odbc_string})


def make_engine(config: DBConfig) -> Engine:
    """Create a SQLAlchemy engine for SQL Server through pyodbc."""

    return create_engine(build_url(config), pool_pre_ping=True)


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
