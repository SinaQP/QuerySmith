"""Configuration loading for QuerySmith."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class DBConfig:
    """SQL Server connection configuration."""

    server: str
    database: str
    username: str
    password: str
    driver: str = "ODBC Driver 17 for SQL Server"
    trusted_connection: bool = False


def _parse_bool(value: str | None) -> bool:
    """Parse a permissive boolean environment value."""

    return value is not None and value.casefold() in {"true", "1", "yes"}


def load_config() -> DBConfig:
    """Load database configuration from environment variables."""

    load_dotenv()
    server = os.getenv("DB_SERVER") or os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    if server and port and "," not in server and "\\" not in server:
        server = f"{server},{port}"

    required_variables = {
        "DB_SERVER or DB_HOST": server,
        "DB_DATABASE or DB_NAME": os.getenv("DB_DATABASE") or os.getenv("DB_NAME"),
        "DB_USERNAME or DB_USER": os.getenv("DB_USERNAME") or os.getenv("DB_USER"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD"),
    }
    missing_variables = [
        name for name, value in required_variables.items() if value is None or value == ""
    ]

    if missing_variables:
        missing = ", ".join(missing_variables)
        raise ValueError(f"Missing required environment variables: {missing}")

    return DBConfig(
        server=required_variables["DB_SERVER or DB_HOST"] or "",
        database=required_variables["DB_DATABASE or DB_NAME"] or "",
        username=required_variables["DB_USERNAME or DB_USER"] or "",
        password=required_variables["DB_PASSWORD"] or "",
        driver=os.getenv("DB_DRIVER") or "ODBC Driver 17 for SQL Server",
        trusted_connection=_parse_bool(os.getenv("DB_TRUSTED_CONNECTION")),
    )
