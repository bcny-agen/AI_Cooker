"""Pluggable recipe generation and enhancement interfaces."""

from recipe_pipeline.generation.enhancer import (
    AIOutputError,
    LLMRecipeEnhancer,
    NoOpRecipeEnhancer,
    RecipeEnhancer,
    TextGenerationClient,
)
from recipe_pipeline.generation.batch import (
    GenerationJob,
    GenerationReport,
    ParallelRetryingGenerationCoordinator,
    PromptedLLMGenerationJobRunner,
    STEP_FLASH_DATASET_VERSION,
    STEP_FLASH_GENERATOR_MODEL,
    StepFlashGenerationJobRunner,
    RetryingGenerationCoordinator,
    build_generation_report,
    create_first_100_plan,
    create_step_flash_200_plan,
)
from recipe_pipeline.generation.codex_dataset import (
    CODEX_GENERATION_MODEL,
    CODEX_GENERATION_PROVIDER,
    CodexAuthoredGenerationJobRunner,
    CodexSegmentRecipeBatchGenerator,
)
from recipe_pipeline.generation.fixture_generator import FixtureRecipeGenerator
from recipe_pipeline.generation.generator import (
    BatchPromptBuilder,
    LLMRecipeBatchGenerator,
    RecipeBatchGenerator,
)
from recipe_pipeline.generation.prompt import (
    DatasetSegment,
    RECIPE_GENERATION_PROMPT_VERSION,
    RecipeGenerationPrompt,
)
from recipe_pipeline.generation.provider import OpenAICompatibleTextClient

__all__ = [
    "AIOutputError",
    "BatchPromptBuilder",
    "CodexAuthoredGenerationJobRunner",
    "CodexSegmentRecipeBatchGenerator",
    "CODEX_GENERATION_MODEL",
    "CODEX_GENERATION_PROVIDER",
    "DatasetSegment",
    "FixtureRecipeGenerator",
    "GenerationJob",
    "GenerationReport",
    "ParallelRetryingGenerationCoordinator",
    "LLMRecipeBatchGenerator",
    "LLMRecipeEnhancer",
    "NoOpRecipeEnhancer",
    "OpenAICompatibleTextClient",
    "PromptedLLMGenerationJobRunner",
    "STEP_FLASH_DATASET_VERSION",
    "STEP_FLASH_GENERATOR_MODEL",
    "StepFlashGenerationJobRunner",
    "RecipeBatchGenerator",
    "RecipeEnhancer",
    "RECIPE_GENERATION_PROMPT_VERSION",
    "RecipeGenerationPrompt",
    "RetryingGenerationCoordinator",
    "TextGenerationClient",
    "build_generation_report",
    "create_first_100_plan",
    "create_step_flash_200_plan",
]
