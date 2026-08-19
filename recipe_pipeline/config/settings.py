"""Environment-backed settings without coupling to the online application."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class PipelineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_provider: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    output_dir: Path = Path("recipe_pipeline/output")
    max_batch_size: int = Field(default=10, ge=1, le=10)
    request_timeout_seconds: float = Field(default=180, ge=10, le=900)
    max_output_tokens: int = Field(default=16_000, ge=1_000, le=64_000)
    temperature: float = Field(default=0.4, ge=0, le=1)

    @property
    def llm_available(self) -> bool:
        return bool(self.model_name and self.api_key and self.base_url)

    @classmethod
    def from_environment(
        cls, dotenv_path: Path | str | None = Path(".env")
    ) -> "PipelineSettings":
        """Read only pipeline-specific settings; never log credential values."""
        if dotenv_path is not None:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("MODEL_BASE_URL")
        return cls(
            llm_provider=(
                os.getenv("LLM_PROVIDER")
                or ("openai-compatible" if base_url else None)
            ),
            model_name=os.getenv("MODEL_NAME") or None,
            api_key=os.getenv("API_KEY") or os.getenv("MODEL_API_KEY") or None,
            base_url=base_url or None,
            output_dir=Path(
                os.getenv("PIPELINE_OUTPUT_DIR", "recipe_pipeline/output")
            ),
            max_batch_size=int(os.getenv("PIPELINE_MAX_BATCH_SIZE", "10")),
            request_timeout_seconds=float(
                os.getenv("PIPELINE_REQUEST_TIMEOUT_SECONDS", "180")
            ),
            max_output_tokens=int(
                os.getenv("PIPELINE_MAX_OUTPUT_TOKENS", "16000")
            ),
            temperature=float(os.getenv("PIPELINE_TEMPERATURE", "0.4")),
        )
