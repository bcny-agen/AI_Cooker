"""Typed settings loaded from environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


class SettingsError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration required by the current AI_Cooker Agent core."""

    model_name: str
    model_api_key: str
    model_base_url: str
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    tavily_api_key: str = ""
    recipe_db_host: str = "127.0.0.1"
    recipe_db_port: int = 55432
    recipe_db_name: str = "recipe_kb"
    recipe_db_user: str = "recipe_kb"
    recipe_db_password: str | None = None
    recipe_db_connect_timeout_seconds: int = 5
    recipe_db_pool_min_size: int = 1
    recipe_db_pool_max_size: int = 4
    recipe_dataset_version: str = "golden_500_v1"
    recipe_embedding_model: str = "intfloat/multilingual-e5-small"
    recipe_embedding_dimension: int = 384
    recipe_embedding_batch_size: int = 16
    recipe_embedding_device: str = "cpu"
    recipe_coverage_policy_version: str = "recipe-coverage-v1"
    recipe_coverage_min_semantic_score: float = 0.80
    recipe_coverage_min_ingredient_ratio: float = 0.50
    recipe_coverage_max_missing_required: int = 3
    image_model_name: str = "step-image-edit-2"
    deepseek_model_name: str = "deepseek-v4-pro"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    demo_image_url: str | None = None
    forum_draft_max_history_characters: int = 24_000
    forum_draft_recent_messages: int = 12
    step_context_window_tokens: int = 256_000
    step_summary_trigger_tokens: int = 64_000
    step_summary_keep_recent_tokens: int = 16_000
    deepseek_context_window_tokens: int = 1_000_000
    deepseek_summary_trigger_tokens: int = 128_000
    deepseek_summary_keep_recent_tokens: int = 24_000
    summary_max_characters: int = 12_000

    @classmethod
    def from_env(
        cls,
        env_file: str | Path | None = DEFAULT_ENV_FILE,
    ) -> "Settings":
        """Load settings without overwriting variables already set by the OS.

        Pass ``env_file=None`` when an environment should not load a .env file,
        such as an isolated unit test or a managed production environment.
        """

        if env_file is not None:
            load_dotenv(dotenv_path=Path(env_file), override=False)

        required_names = (
            "MODEL_NAME",
            "MODEL_API_KEY",
            "MODEL_BASE_URL",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DATABASE",
        )
        values = {name: os.getenv(name) for name in required_names}
        missing = [
            name
            for name, value in values.items()
            if value is None or not value.strip()
        ]
        if missing:
            joined = ", ".join(missing)
            raise SettingsError(f"Missing required environment variables: {joined}")

        try:
            mysql_port = int(values["MYSQL_PORT"] or "")
        except ValueError as exc:
            raise SettingsError("MYSQL_PORT must be an integer.") from exc

        if not 1 <= mysql_port <= 65535:
            raise SettingsError("MYSQL_PORT must be between 1 and 65535.")

        try:
            recipe_db_port = int(os.getenv("RECIPE_DB_PORT", "55432"))
            recipe_db_connect_timeout_seconds = int(os.getenv(
                "RECIPE_DB_CONNECT_TIMEOUT_SECONDS",
                "5",
            ))
            recipe_db_pool_min_size = int(os.getenv(
                "RECIPE_DB_POOL_MIN_SIZE",
                "1",
            ))
            recipe_db_pool_max_size = int(os.getenv(
                "RECIPE_DB_POOL_MAX_SIZE",
                "4",
            ))
            recipe_embedding_dimension = int(os.getenv(
                "RECIPE_EMBEDDING_DIMENSION",
                os.getenv("RECIPE_EMBEDDING_DIMENSIONS", "384"),
            ))
            recipe_embedding_batch_size = int(os.getenv(
                "RECIPE_EMBEDDING_BATCH_SIZE",
                "16",
            ))
            recipe_coverage_min_semantic_score = float(os.getenv(
                "RECIPE_COVERAGE_MIN_SEMANTIC_SCORE",
                "0.80",
            ))
            recipe_coverage_min_ingredient_ratio = float(os.getenv(
                "RECIPE_COVERAGE_MIN_INGREDIENT_RATIO",
                "0.50",
            ))
            recipe_coverage_max_missing_required = int(os.getenv(
                "RECIPE_COVERAGE_MAX_MISSING_REQUIRED",
                "3",
            ))
        except ValueError as exc:
            raise SettingsError("Recipe KB numeric settings are invalid.") from exc
        if not 1 <= recipe_db_port <= 65535:
            raise SettingsError("RECIPE_DB_PORT must be between 1 and 65535.")
        if recipe_db_connect_timeout_seconds < 1:
            raise SettingsError(
                "RECIPE_DB_CONNECT_TIMEOUT_SECONDS must be positive."
            )
        if not 1 <= recipe_db_pool_min_size <= recipe_db_pool_max_size <= 32:
            raise SettingsError(
                "Recipe DB pool sizes must satisfy 1 <= min <= max <= 32."
            )
        if recipe_embedding_dimension < 1 or recipe_embedding_batch_size < 1:
            raise SettingsError("Recipe embedding settings must be positive.")
        if not 0.0 <= recipe_coverage_min_semantic_score <= 1.0:
            raise SettingsError(
                "RECIPE_COVERAGE_MIN_SEMANTIC_SCORE must be between 0 and 1."
            )
        if not 0.0 <= recipe_coverage_min_ingredient_ratio <= 1.0:
            raise SettingsError(
                "RECIPE_COVERAGE_MIN_INGREDIENT_RATIO must be between 0 and 1."
            )
        if recipe_coverage_max_missing_required < 0:
            raise SettingsError(
                "RECIPE_COVERAGE_MAX_MISSING_REQUIRED must not be negative."
            )

        demo_image_url = os.getenv("DEMO_IMAGE_URL")

        try:
            forum_draft_max_history_characters = int(os.getenv(
                "FORUM_DRAFT_MAX_HISTORY_CHARACTERS",
                "24000",
            ))
            forum_draft_recent_messages = int(os.getenv(
                "FORUM_DRAFT_RECENT_MESSAGES",
                "12",
            ))
            step_context_window_tokens = int(os.getenv(
                "STEP_CONTEXT_WINDOW_TOKENS",
                "256000",
            ))
            step_summary_trigger_tokens = int(os.getenv(
                "STEP_SUMMARY_TRIGGER_TOKENS",
                "64000",
            ))
            step_summary_keep_recent_tokens = int(os.getenv(
                "STEP_SUMMARY_KEEP_RECENT_TOKENS",
                "16000",
            ))
            deepseek_context_window_tokens = int(os.getenv(
                "DEEPSEEK_CONTEXT_WINDOW_TOKENS",
                "1000000",
            ))
            deepseek_summary_trigger_tokens = int(os.getenv(
                "DEEPSEEK_SUMMARY_TRIGGER_TOKENS",
                "128000",
            ))
            deepseek_summary_keep_recent_tokens = int(os.getenv(
                "DEEPSEEK_SUMMARY_KEEP_RECENT_TOKENS",
                "24000",
            ))
            summary_max_characters = int(os.getenv(
                "SUMMARY_MAX_CHARACTERS",
                "12000",
            ))
        except ValueError as exc:
            raise SettingsError(
                "History and context settings must be integers."
            ) from exc
        if not 1_000 <= forum_draft_max_history_characters <= 100_000:
            raise SettingsError(
                "FORUM_DRAFT_MAX_HISTORY_CHARACTERS must be between 1000 and 100000."
            )
        if not 2 <= forum_draft_recent_messages <= 50:
            raise SettingsError(
                "FORUM_DRAFT_RECENT_MESSAGES must be between 2 and 50."
            )
        cls._validate_context_policy(
            "STEP",
            step_context_window_tokens,
            step_summary_trigger_tokens,
            step_summary_keep_recent_tokens,
        )
        cls._validate_context_policy(
            "DEEPSEEK",
            deepseek_context_window_tokens,
            deepseek_summary_trigger_tokens,
            deepseek_summary_keep_recent_tokens,
        )
        if not 1_000 <= summary_max_characters <= 50_000:
            raise SettingsError(
                "SUMMARY_MAX_CHARACTERS must be between 1000 and 50000."
            )

        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        image_model_name = os.getenv(
            "STEP_IMAGE_MODEL",
            "step-image-edit-2",
        ).strip()
        if image_model_name != "step-image-edit-2":
            raise SettingsError(
                "STEP_IMAGE_MODEL currently supports only step-image-edit-2."
            )
        return cls(
            model_name=(values["MODEL_NAME"] or "").strip(),
            model_api_key=values["MODEL_API_KEY"] or "",
            model_base_url=(values["MODEL_BASE_URL"] or "").strip(),
            deepseek_model_name=os.getenv(
                "DEEPSEEK_MODEL_NAME",
                "deepseek-v4-pro",
            ).strip(),
            deepseek_api_key=(
                deepseek_api_key.strip() if deepseek_api_key else None
            ),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            ).strip(),
            mysql_host=(values["MYSQL_HOST"] or "").strip(),
            mysql_port=mysql_port,
            mysql_user=values["MYSQL_USER"] or "",
            mysql_password=values["MYSQL_PASSWORD"] or "",
            mysql_database=(values["MYSQL_DATABASE"] or "").strip(),
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            recipe_db_host=os.getenv("RECIPE_DB_HOST", "127.0.0.1").strip(),
            recipe_db_port=recipe_db_port,
            recipe_db_name=os.getenv("RECIPE_DB_NAME", "recipe_kb").strip(),
            recipe_db_user=os.getenv("RECIPE_DB_USER", "recipe_kb").strip(),
            recipe_db_password=(
                os.getenv("RECIPE_DB_PASSWORD", "").strip() or None
            ),
            recipe_db_connect_timeout_seconds=(
                recipe_db_connect_timeout_seconds
            ),
            recipe_db_pool_min_size=recipe_db_pool_min_size,
            recipe_db_pool_max_size=recipe_db_pool_max_size,
            recipe_dataset_version=os.getenv(
                "RECIPE_DATASET_VERSION",
                "golden_500_v1",
            ).strip(),
            recipe_embedding_model=os.getenv(
                "RECIPE_EMBEDDING_MODEL",
                "intfloat/multilingual-e5-small",
            ).strip(),
            recipe_embedding_dimension=recipe_embedding_dimension,
            recipe_embedding_batch_size=recipe_embedding_batch_size,
            recipe_embedding_device=os.getenv(
                "RECIPE_EMBEDDING_DEVICE",
                "cpu",
            ).strip(),
            recipe_coverage_policy_version=os.getenv(
                "RECIPE_COVERAGE_POLICY_VERSION",
                "recipe-coverage-v1",
            ).strip(),
            recipe_coverage_min_semantic_score=(
                recipe_coverage_min_semantic_score
            ),
            recipe_coverage_min_ingredient_ratio=(
                recipe_coverage_min_ingredient_ratio
            ),
            recipe_coverage_max_missing_required=(
                recipe_coverage_max_missing_required
            ),
            image_model_name=image_model_name,
            demo_image_url=(demo_image_url.strip() if demo_image_url else None),
            forum_draft_max_history_characters=(
                forum_draft_max_history_characters
            ),
            forum_draft_recent_messages=forum_draft_recent_messages,
            step_context_window_tokens=step_context_window_tokens,
            step_summary_trigger_tokens=step_summary_trigger_tokens,
            step_summary_keep_recent_tokens=step_summary_keep_recent_tokens,
            deepseek_context_window_tokens=deepseek_context_window_tokens,
            deepseek_summary_trigger_tokens=deepseek_summary_trigger_tokens,
            deepseek_summary_keep_recent_tokens=(
                deepseek_summary_keep_recent_tokens
            ),
            summary_max_characters=summary_max_characters,
        )

    @staticmethod
    def _validate_context_policy(
        prefix: str,
        context_window_tokens: int,
        trigger_tokens: int,
        keep_recent_tokens: int,
    ) -> None:
        if context_window_tokens < 1_000:
            raise SettingsError(
                f"{prefix}_CONTEXT_WINDOW_TOKENS must be at least 1000."
            )
        safe_input_tokens = int(context_window_tokens * 0.8)
        if not 100 <= trigger_tokens < safe_input_tokens:
            raise SettingsError(
                f"{prefix}_SUMMARY_TRIGGER_TOKENS must be at least 100 "
                f"and smaller than 80% of "
                f"{prefix}_CONTEXT_WINDOW_TOKENS."
            )
        if not 1 <= keep_recent_tokens < trigger_tokens:
            raise SettingsError(
                f"{prefix}_SUMMARY_KEEP_RECENT_TOKENS must be positive "
                f"and smaller than {prefix}_SUMMARY_TRIGGER_TOKENS."
            )

    @property
    def mysql_uri(self) -> str:
        """Build a standards-compliant MySQL URI without exposing it in logs."""

        host = self.mysql_host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"

        user = quote(self.mysql_user, safe="")
        password = quote(self.mysql_password, safe="")
        database = quote(self.mysql_database, safe="")
        return f"mysql://{user}:{password}@{host}:{self.mysql_port}/{database}"
