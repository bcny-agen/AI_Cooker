"""Concrete OpenAI-compatible text client for offline generation runs."""

from __future__ import annotations

from openai import OpenAI

from recipe_pipeline.generation.enhancer import AIOutputError


class OpenAICompatibleTextClient:
    """Small adapter using JSON Mode; all returned JSON is still schema-validated."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 180,
        max_output_tokens: int = 16_000,
        temperature: float = 0.4,
    ):
        if not api_key or not base_url or not model_name:
            raise ValueError("api_key, base_url and model_name are required")
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._model_name = model_name
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You produce safe, realistic household recipe data as "
                            "strict machine-readable JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=self._temperature,
                max_tokens=self._max_output_tokens,
            )
        except Exception as exc:
            raise AIOutputError(
                f"LLM generation request failed ({type(exc).__name__})"
            ) from exc
        if not response.choices:
            raise AIOutputError("LLM generation returned no choices")
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise AIOutputError("LLM generation returned empty content")
        return content
