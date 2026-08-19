"""Evaluation-only retrieval policy variants; production stays RAG-first."""

from __future__ import annotations

from app.agent.prompts import COOKER_SYSTEM_PROMPT
from recipe_pipeline.agent_eval.models import EvaluationStrategy


_RAG_POLICY_START = "2. 智能食谱检索："
_RAG_POLICY_END = "4. 多维度评估与排序："

_LEGACY_RETRIEVAL_BLOCK = """2. 智能食谱检索（评估基线）：普通食谱推荐、按食材找菜、替代食材和烹饪方法，优先调用 web_search，以当前网页结果作为主要知识来源。若来自照片，把识别出的食材写进网页搜索词，并保留用户的过敏、忌口、饮食和设备限制。
3. 网页优先策略（评估基线）：不要先调用 recipe_search。只有 web_search 不可用而回答仍需要食谱证据时，才可调用 recipe_search。用户明确要求最新趋势、当前网页来源或在线参考时，必须调用 web_search。
3a. 工具参数与记忆约束：如果系统上下文提供了与本次请求相关的稳定饮食记忆（例如避开香菜、少油、素食、过敏），调用 recipe_search 时也必须把它们映射到 excluded_ingredients、excluded_allergens、dietary_constraints 或 taste_preferences；不要只在最终文字里提及。应用层会在工具执行前确定性合并这些约束；不得删除或弱化应用层约束。
3b. 流式工具调用纪律：需要调用任何工具时，该次工具请求消息只输出工具调用，不要同时输出面向用户的正文、推理过程或“我先搜索”等过渡文字。所有面向用户的最终正文必须放在工具调用完成后的独立最终助手消息中。"""


def prompt_for_strategy(strategy: EvaluationStrategy) -> str:
    if strategy == EvaluationStrategy.RECIPE_RAG_FIRST:
        return COOKER_SYSTEM_PROMPT
    start = COOKER_SYSTEM_PROMPT.find(_RAG_POLICY_START)
    end = COOKER_SYSTEM_PROMPT.find(_RAG_POLICY_END)
    if start < 0 or end <= start:
        raise RuntimeError(
            "Production prompt changed; review the evaluation-only legacy transform."
        )
    return (
        COOKER_SYSTEM_PROMPT[:start]
        + _LEGACY_RETRIEVAL_BLOCK
        + "\n"
        + COOKER_SYSTEM_PROMPT[end:]
    )


def tool_description_for_strategy(
    strategy: EvaluationStrategy,
    tool_name: str,
    production_description: str,
) -> str:
    """Resolve policy text only; schemas and tool implementations stay identical."""

    if strategy == EvaluationStrategy.RECIPE_RAG_FIRST:
        return production_description
    if tool_name == "web_search":
        return (
            "Evaluation-only Legacy baseline: use this as the primary retrieval "
            "source for ordinary recipe recommendations, ingredient cooking ideas, "
            "substitutions, cooking methods, and current-web requests. Preserve all "
            "user exclusions, allergies, dietary, time, and equipment constraints "
            "in the search query."
        )
    if tool_name == "recipe_search":
        return (
            "Evaluation-only Legacy fallback backed by AI_Cooker's curated Recipe "
            "Knowledge Base. Do not call this before web_search. Call it only if "
            "web_search is unavailable and grounded recipe evidence is still needed. "
            "When called, pass every known ingredient and hard constraint."
        )
    return production_description
