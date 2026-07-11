"""
科研意图检测 + 自动上下文注入 PhaseModule

在 BeforeReasoning 阶段检测用户问题是否与研究相关，
若是则自动检索论文和图谱，在 PromptRender 阶段注入上下文。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from agent.lifecycle.types import BeforeReasoningCtx, PromptRenderCtx
from agent.prompting.assembler import PromptSectionRender

logger = logging.getLogger(__name__)

# Slot 名称常量
SLOT_RESEARCH_QUERY = "research:user_query"         # 原始查询文本
SLOT_RESEARCH_RESULTS = "research:auto_context"      # 检索结果文本
SLOT_RESEARCH_ENABLED = "research:enabled"           # 模块启用标记


class ResearchContextModule:
    """
    BeforeReasoning 阶段模块
    - 检测用户输入是否与研究相关
    - 若是则自动调用论文知识库和图谱检索
    - 结果存入 frame.slots 供后续阶段使用
    """

    slot = SLOT_RESEARCH_QUERY
    requires = ("before_turn.acquire_session", "session:session")
    produces = (SLOT_RESEARCH_QUERY, SLOT_RESEARCH_RESULTS, SLOT_RESEARCH_ENABLED)

    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    async def run(self, frame: Any) -> Any:
        # 检查插件是否启用且有检索能力
        plugin = self._plugin
        if not plugin.is_active():
            frame.slots[SLOT_RESEARCH_ENABLED] = False
            return frame

        # 检查是否已注入（避免重复）
        if SLOT_RESEARCH_RESULTS in frame.slots:
            return frame

        # 获取用户输入
        ctx = cast(BeforeReasoningCtx, frame.input)
        user_input = ctx.content.strip()
        if not user_input or len(user_input) < 5:
            frame.slots[SLOT_RESEARCH_ENABLED] = False
            return frame

        detector = getattr(plugin, "_intent_detector", None)
        if not detector:
            frame.slots[SLOT_RESEARCH_ENABLED] = False
            return frame

        # 意图检测
        try:
            is_research, confidence = await detector.is_research_query(user_input)
        except Exception as e:
            logger.debug("Intent detection error: %s", e)
            frame.slots[SLOT_RESEARCH_ENABLED] = False
            return frame

        frame.slots[SLOT_RESEARCH_ENABLED] = is_research
        frame.slots[SLOT_RESEARCH_QUERY] = user_input

        if not is_research:
            return frame

        # 自动检索论文和图谱
        results = await self._auto_retrieve(user_input, plugin)
        if results:
            frame.slots[SLOT_RESEARCH_RESULTS] = results

        return frame

    async def _auto_retrieve(self, query: str, plugin: Any) -> str | None:
        """自动检索论文和图谱，返回格式化上下文文本"""
        embedder = getattr(plugin, "embedder", None)
        vector_retriever = getattr(plugin, "vector_retriever", None)
        keyword_retriever = getattr(plugin, "keyword_retriever", None)
        fusion = getattr(plugin, "fusion", None)
        graphrag = getattr(plugin, "graphrag", None)

        if not embedder or not vector_retriever:
            return None

        try:
            # 向量检索
            query_emb = await embedder.embed_text(query)
            vector_results = await vector_retriever.search_chunks(query_emb, top_k=5)
        except Exception as e:
            logger.debug("Vector search failed: %s", e)
            vector_results = []

        # 关键词检索
        keyword_results = []
        if keyword_retriever:
            try:
                keyword_results = await keyword_retriever.search_chunks(query, top_k=5)
            except Exception as e:
                logger.debug("Keyword search failed: %s", e)

        # RRF 融合
        if fusion and (vector_results or keyword_results):
            fused = fusion.fuse(vector_results, keyword_results)
            top_results = fused[:5]
        else:
            top_results = (vector_results + keyword_results)[:5]

        if not top_results:
            return None

        # 图谱上下文
        graph_lines = []
        if graphrag:
            try:
                gc = await graphrag.format_entity_context(query, max_entities=3)
                if gc:
                    graph_lines.append(gc)
            except Exception as e:
                logger.debug("GraphRAG search failed: %s", e)

        # 格式化注入文本（控制长度）
        lines = ["## 自动检索：相关论文片段\n"]
        chars = 0
        max_chars = 800  # 自动注入不超过 800 字符

        for r in top_results:
            title = r.get("paper_title", "Unknown")[:60]
            section = r.get("section", "")
            content = r.get("content", "")[:250].replace("\n", " ")
            score = r.get("fusion_score", r.get("score", 0))

            entry = f"- **{title}** [{section}] (score: {score:.2f})\n  {content}\n"
            if chars + len(entry) > max_chars:
                break
            lines.append(entry)
            chars += len(entry)

        if graph_lines:
            for gl in graph_lines:
                if chars + len(gl) > max_chars:
                    break
                lines.append(gl)
                chars += len(gl)

        return "\n".join(lines)


class ResearchPromptInjectModule:
    """
    PromptRender 阶段模块
    - 读取 BeforeReasoning 阶段检测到的研究上下文
    - 注入到 system_prompt 底部
    """

    slot = "research:injected"
    requires = (SLOT_RESEARCH_ENABLED,)
    produces = ("research:injected",)

    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    async def run(self, frame: Any) -> Any:
        if not frame.slots.get(SLOT_RESEARCH_ENABLED):
            return frame

        research_context = frame.slots.get(SLOT_RESEARCH_RESULTS)
        if not research_context:
            return frame

        ctx = cast(PromptRenderCtx, frame.input)
        ctx.system_sections_bottom.append(
            PromptSectionRender(
                name="research_auto_context",
                content=research_context,
                is_static=False,
            )
        )
        frame.slots["research:injected"] = True

        logger.debug(
            "Injected research context (%d chars) into prompt",
            len(research_context),
        )
        return frame
