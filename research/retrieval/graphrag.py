"""
GraphRAG 图谱增强检索

基于 Neo4j 知识图谱的方法/数据集/指标关系查询。
"""

from __future__ import annotations

import logging
from typing import Any

from research.graph.driver import ResearchGraph
from research.graph.schema import *

logger = logging.getLogger(__name__)


class GraphRAGRetriever:
    """基于 Neo4j 知识图谱的增强检索"""

    def __init__(self, graph: ResearchGraph):
        self.graph = graph

    async def search_by_method(self, method_name: str) -> list[dict[str, Any]]:
        """
        查询某个方法的关系网络。

        Returns:
            [{relation, target, target_type}, ...]
        """
        result = await self.graph.run_query(
            RELATIONS_AROUND_METHOD_CYPHER,
            {"method_name": method_name},
        )
        return result

    async def get_methods_on_dataset(
        self, dataset: str, metric_name: str = "mAP"
    ) -> list[dict[str, Any]]:
        """
        查询在某数据集上评估的各方法及指标。

        Args:
            dataset: 数据集名（如 "DOTA-v1.0", "DIOR"）
            metric_name: 指标名（如 "mAP", "F1"）

        Returns:
            [{method, metrics, values}, ...]
        """
        result = await self.graph.run_query(
            METHODS_ON_DATASET_CYPHER,
            {"dataset": dataset, "metric_name": metric_name},
        )
        return result

    async def get_methods_by_concept(self, concept: str) -> list[dict[str, Any]]:
        """
        查询包含某概念的所有方法。

        Args:
            concept: 概念名（如 "uncertainty_sampling", "consistency_regularization"）

        Returns:
            [{method, papers, datasets}, ...]
        """
        result = await self.graph.run_query(
            METHODS_BY_CONCEPT_CYPHER,
            {"concept": concept},
        )
        return result

    async def search_entities(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        模糊搜索知识图谱中的实体。

        Args:
            query: 搜索关键词
            limit: 最大返回数

        Returns:
            [{name, type, description}, ...]
        """
        result = await self.graph.run_query("""
            MATCH (e)
            WHERE e.name CONTAINS $query OR e.description CONTAINS $query
            RETURN e.name AS name,
                   head(labels(e)) AS type,
                   e.description AS description
            LIMIT $limit
        """, {"query": query, "limit": limit})
        return result

    async def format_method_comparison(
        self, dataset: str, metric_name: str = "mAP"
    ) -> str:
        """
        生成某数据集上的方法对比文本（供 LLM 上下文使用）。

        Returns:
            格式化后的 Markdown 对比表
        """
        results = await self.get_methods_on_dataset(dataset, metric_name)
        if not results:
            return f"（知识图谱中暂无 {dataset} 上的 {metric_name} 数据）"

        lines = [f"## {dataset} 上各方法的 {metric_name} 对比\n"]
        lines.append("| 方法 | 指标 | 数值 |")
        lines.append("|------|------|------|")
        for r in results:
            metrics = r.get("metrics", [])
            values = r.get("values", [])
            for m, v in zip(metrics, values):
                lines.append(f"| {r['method']} | {m} | {v} |")
        return "\n".join(lines)

    async def format_entity_context(
        self, query: str, max_entities: int = 5
    ) -> str:
        """
        从查询中提取相关实体，生成图谱上下文文本（供 LLM 注入）。

        Args:
            query: 用户查询
            max_entities: 最大实体数

        Returns:
            图谱上下文文本，空字符串表示无结果
        """
        entities = await self.search_entities(query, limit=max_entities)
        if not entities:
            return ""

        lines = ["## 知识图谱相关实体\n"]
        for ent in entities:
            name = ent.get("name", "")
            etype = ent.get("type", "")
            desc = ent.get("description", "")

            # 查询该实体的关系
            rels = await self.graph.run_query(
                "MATCH (e {name: $name})-[r]-(connected) "
                "RETURN type(r) AS rel, connected.name AS target, "
                "       head(labels(connected)) AS target_type "
                "LIMIT 8",
                {"name": name},
            )
            rel_str = "; ".join(
                f"{r['rel']}({r['target']})" for r in rels
            ) if rels else "（无直接关系）"

            lines.append(f"- **{name}** ({etype}): {desc[:100]}")
            lines.append(f"  - 关系: {rel_str}")

        return "\n".join(lines)
