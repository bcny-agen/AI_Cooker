"""Database connection, readiness, migration, and extension checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recipe_pipeline.recipe_kb.config import RecipeKBConfig


class RecipeKBUnavailableError(RuntimeError):
    pass


class PgvectorUnavailableError(RuntimeError):
    pass


class MigrationError(RuntimeError):
    pass


MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def connect(config: RecipeKBConfig, *, autocommit: bool = False):
    try:
        import psycopg
    except ImportError as error:
        raise RecipeKBUnavailableError(
            "psycopg[binary] is required for the Recipe Knowledge Base"
        ) from error
    try:
        return psycopg.connect(**config.connection_kwargs, autocommit=autocommit)
    except psycopg.Error as error:
        raise RecipeKBUnavailableError(
            f"Recipe PostgreSQL is unavailable at {config.host}:{config.port}"
        ) from error


def readiness(config: RecipeKBConfig) -> dict[str, Any]:
    with connect(config) as connection:
        row = connection.execute(
            """
            SELECT current_setting('server_version'),
                   (SELECT extversion FROM pg_extension WHERE extname = 'vector')
            """
        ).fetchone()
    if not row[1]:
        raise PgvectorUnavailableError("CREATE EXTENSION vector has not been applied")
    return {"ready": True, "postgresql_version": row[0], "pgvector_version": row[1]}


def apply_migrations(config: RecipeKBConfig) -> list[str]:
    applied: list[str] = []
    try:
        with connect(config) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recipe_kb_schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            existing = {
                row[0]
                for row in connection.execute(
                    "SELECT version FROM recipe_kb_schema_migrations"
                ).fetchall()
            }
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = path.stem
                if version in existing:
                    continue
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO recipe_kb_schema_migrations(version) VALUES (%s)",
                    (version,),
                )
                applied.append(version)
    except Exception as error:
        if isinstance(error, (RecipeKBUnavailableError, PgvectorUnavailableError)):
            raise
        raise MigrationError("Recipe KB migration failed and was rolled back") from error
    readiness(config)
    return applied
