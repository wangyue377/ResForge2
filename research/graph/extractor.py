"""
LLM 驱动的知识图谱实体/关系提取

从论文文本块中提取科研实体（方法、数据集、指标等）及其关系，
参考 WeKnora graph.go 的 graphBuilder 设计。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENTITY_EXTRACTION_PROMPT = """你是一个科研知识图谱构建助手。从以下论文段落中提取实体和关系。

论文标题: {title}
段落内容:
{content}

请提取以下类型的实体（不存在则不提取）：
1. Method — 方法名（如 Mean Teacher, FixMatch, ActiveTeacher, Soft Teacher）
2. Dataset — 数据集名（如 DOTA, DIOR, HRSC2016, FAIR1M）
3. Architecture — 网络架构（如 Faster R-CNN, YOLOv8, ResNet-50, Swin-T）
4. Metric — 评估指标（如 mAP, F1-score, precision, recall）及其数值
5. Concept — 学术概念（如 consistency regularization, uncertainty sampling, pseudo-labeling）

并提取实体之间的关系：
- Method COMPOSED_OF Concept   — 方法包含什么概念
- Method USES Dataset          — 方法在哪个数据集上评估
- Method ACHIEVES Metric       — 方法达到什么指标结果（包含数值）
- Method BASED_ON Method       — 基于哪个方法改进

用中文描述每个实体的 description。

返回 JSON 格式：
{{
  "entities": [
    {{"name": "ActiveTeacher", "type": "Method", "description": "一种用于半监督目标检测的主动学习方法"}},
    {{"name": "DOTA-v1.0", "type": "Dataset", "description": "遥感图像目标检测常用基准数据集"}}
  ],
  "relationships": [
    {{"source": "ActiveTeacher", "target": "DOTA-v1.0", "type": "USES", "properties": {{}}}},
    {{"source": "ActiveTeacher", "target": "uncertainty_sampling", "type": "COMPOSED_OF", "properties": {{}}}}
  ]
}}

只返回 JSON，不要其他文字。
"""


class GraphExtractor:
    """LLM 驱动实体关系提取器"""

    def __init__(self, llm_provider: Any):
        """
        Args:
            llm_provider: 具有 chat_completion 接口的 LLM provider
                          建议用快速/轻量模型（如 Qwen-Flash）
        """
        self.llm = llm_provider

    async def extract_from_chunk(
        self, title: str, content: str, chunk_index: int = 0
    ) -> dict:
        """
        从单个文本块中提取实体和关系。

        Returns:
            {"entities": [...], "relationships": [...]}
        """
        prompt = ENTITY_EXTRACTION_PROMPT.format(
            title=title,
            content=content[:3000],  # 限制输入长度
        )
        try:
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = response["choices"][0]["message"]["content"]
            result = json.loads(content)
            entities = result.get("entities", [])
            relationships = result.get("relationships", [])
            logger.debug(
                "Extracted %d entities, %d relationships from chunk %d",
                len(entities), len(relationships), chunk_index,
            )
            return result
        except Exception as e:
            logger.warning("Entity extraction failed for chunk %d: %s", chunk_index, e)
            return {"entities": [], "relationships": []}

    async def extract_batch(
        self, title: str, chunks: list[dict], max_chunks: int = 5
    ) -> dict:
        """
        批量提取（取论文的前 N 个块，避免 Token 超限）。

        Returns:
            合并后的 {"entities": [...], "relationships": [...]}
        """
        all_entities: list[dict] = []
        all_relationships: list[dict] = []
        seen_entities = set()
        seen_rels = set()

        for chunk in chunks[:max_chunks]:
            result = await self.extract_from_chunk(
                title=title,
                content=chunk["content"],
                chunk_index=chunk["chunk_index"],
            )
            # 去重
            for e in result.get("entities", []):
                key = (e.get("name", ""), e.get("type", ""))
                if key not in seen_entities:
                    seen_entities.add(key)
                    all_entities.append(e)
            for r in result.get("relationships", []):
                key = (r.get("source", ""), r.get("type", ""), r.get("target", ""))
                if key not in seen_rels:
                    seen_rels.add(key)
                    all_relationships.append(r)

        return {
            "entities": all_entities,
            "relationships": all_relationships,
        }
