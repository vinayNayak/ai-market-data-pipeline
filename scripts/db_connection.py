"""PostgreSQL connection helpers for the AI market data pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

import psycopg
from psycopg import Connection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SSL_PARAMS = "sslmode=require&channel_binding=require"
DEFAULT_DB_HOST = "ep-orange-mouse-admjg3nn-pooler.c-2.us-east-1.aws.neon.tech"
DEFAULT_DB_USER = "neondb_owner"
DEFAULT_DB_NAME = "neondb"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file without overriding existing env vars."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def build_connection_url() -> str:
    """Return a PostgreSQL connection URL from environment variables."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    password = os.getenv("DB_PASSWORD")
    if not password:
        raise ValueError(
            "Database credentials missing. Set DATABASE_URL or DB_PASSWORD "
            "in the environment or project .env file."
        )

    user = os.getenv("DB_USER", DEFAULT_DB_USER)
    host = os.getenv("DB_HOST", DEFAULT_DB_HOST)
    name = os.getenv("DB_NAME", DEFAULT_DB_NAME)

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}/{name}?{DEFAULT_SSL_PARAMS}"
    )


def connect(*, load_env: bool = True) -> Connection:
    """Open a new PostgreSQL connection."""
    if load_env:
        load_dotenv()
    return psycopg.connect(build_connection_url())


if __name__ == "__main__":
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
    print("Connected successfully")
    print(version.split(",")[0])
