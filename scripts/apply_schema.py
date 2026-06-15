"""Apply database migrations with yoyo-migrations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yoyo import get_backend, read_migrations

from db_connection import PROJECT_ROOT, build_yoyo_database_url
from dotenv import load_dotenv

DEFAULT_MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def list_migrations(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[tuple[str, str]]:
    """Return migration id and status pairs."""
    _load_env()
    backend = get_backend(build_yoyo_database_url())
    migrations = read_migrations(str(migrations_dir))
    return [
        (migration.id, "applied" if backend.is_applied(migration) else "pending")
        for migration in migrations
    ]


def apply_schema(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations and return their ids."""
    _load_env()
    backend = get_backend(build_yoyo_database_url())
    migrations = read_migrations(str(migrations_dir))
    to_apply = backend.to_apply(migrations)

    with backend.lock():
        backend.apply_migrations(to_apply)

    return [migration.id for migration in to_apply]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply yoyo database migrations for the AI market data pipeline."
    )
    parser.add_argument(
        "--migrations",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help=f"Path to migrations directory (default: {DEFAULT_MIGRATIONS_DIR})",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List migrations and their status without applying",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.list:
            rows = list_migrations(args.migrations)
            print(f"Migrations in {args.migrations}:")
            for migration_id, status in rows:
                print(f"  [{status}] {migration_id}")
            return 0

        applied = apply_schema(args.migrations)
    except Exception as exc:
        print(f"Schema apply failed: {exc}", file=sys.stderr)
        return 1

    if applied:
        print(f"Applied {len(applied)} migration(s):")
        for migration_id in applied:
            print(f"  - {migration_id}")
    else:
        print("No pending migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
