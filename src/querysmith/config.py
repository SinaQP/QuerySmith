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


def load_config() -> DBConfig:
    """Load database configuration from environment variables."""

    load_dotenv()

    required_variables = {
        "QUERYSMITH_SERVER": os.getenv("QUERYSMITH_SERVER"),
        "QUERYSMITH_DATABASE": os.getenv("QUERYSMITH_DATABASE"),
        "QUERYSMITH_USERNAME": os.getenv("QUERYSMITH_USERNAME"),
        "QUERYSMITH_PASSWORD": os.getenv("QUERYSMITH_PASSWORD"),
    }
    missing_variables = [
        name for name, value in required_variables.items() if value is None or value == ""
    ]

    if missing_variables:
        missing = ", ".join(missing_variables)
        raise ValueError(f"Missing required environment variables: {missing}")

    return DBConfig(
        server=required_variables["QUERYSMITH_SERVER"] or "",
        database=required_variables["QUERYSMITH_DATABASE"] or "",
        username=required_variables["QUERYSMITH_USERNAME"] or "",
        password=required_variables["QUERYSMITH_PASSWORD"] or "",
        driver=os.getenv("QUERYSMITH_DRIVER") or "ODBC Driver 17 for SQL Server",
    )
