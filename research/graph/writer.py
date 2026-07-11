"""
Neo4j 知识图谱写入器

将 LLM 提取的实体和关系写入 Neo4j 图数据库。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from research.graph.driver import ResearchGraph
from research.graph.schema import *

logger = logging.getLogger(__name__)


def _safe_param(key: str) -> str:
    """将属性名转为合法 Cypher 参数名（不能数字开头、不能含特殊字符）"""
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", key)
    if safe and safe[0].isdigit():
        safe = f"p_{safe}"
    return safe or "_prop"


def _safe_prop(key: str) -> str:
    """对不合语法的 Cypher 属性名加反引号"""
    if not key:
        return "``"
    if key[0].isalpha() and key.isidentifier():
        return key
    return f"`{key}`"

# 标签映射：代码类型名 → Neo4j 标签
TYPE_TO_LABEL = {
    "Method": METHOD,
    "Dataset": DATASET,
    "Architecture": ARCHITECTURE,
    "Metric": METRIC,
    "Concept": CONCEPT,
    "Paper": PAPER,
    "Author": AUTHOR,
    "CodeRepository": CODE_REPO,
}


class GraphWriter:
    """将实体关系写入 Neo4j"""

    def __init__(self, graph: ResearchGraph):
        self.graph = graph

    async def init_schema(self):
        """初始化 Neo4j 约束和索引"""
        statements = INIT_SCHEMA_CYPHER.split(";")
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                try:
                    await self.graph.run_query(stmt)
                except Exception as e:
                    logger.warning("Schema init statement warning: %s", e)
        logger.info("Neo4j schema initialized")

    async def write_paper_entities(
        self,
        paper_id: str,
        title: str,
        entities: list[dict],
        relationships: list[dict],
    ):
        """
        写入一篇论文的实体和关系到 Neo4j。

        Args:
            paper_id: ArXiv ID 或论文内部 ID
            title: 论文标题
            entities: [{name, type, description}, ...]
            relationships: [{source, target, type, properties}, ...]
        """
        # ① 确保 Paper 节点存在
        await self.graph.run_query("""
            MERGE (p:Paper {arxiv_id: $paper_id})
            ON CREATE SET p.title = $title, p.created_at = datetime()
            ON MATCH SET p.title = $title
        """, {"paper_id": paper_id, "title": title})

        # ② 写入实体节点 + 关联到论文
        for ent in entities:
            label = TYPE_TO_LABEL.get(ent.get("type", ""), "Entity")
            name = ent.get("name", "")
            desc = ent.get("description", "")

            if not name:
                continue

            # MERGE 节点（去重）
            await self.graph.run_query(f"""
                MERGE (e:{label} {{name: $name}})
                ON CREATE SET e.description = $desc, e.created_at = datetime()
            """, {"name": name, "desc": desc})

            # 关联 Paper → Method
            await self.graph.run_query("""
                MATCH (p:Paper {arxiv_id: $paper_id})
                MATCH (e {name: $name})
                MERGE (p)-[:PROPOSES]->(e)
            """, {"paper_id": paper_id, "name": name})

        # ③ 写入关系
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("type", "")
            props = rel.get("properties", {})

            if not source or not target or not rel_type:
                continue

            # 将 ACHIEVES 的 value 属性存入关系（处理属性名含特殊字符或数字开头）
            safe_props = {}
            props_parts = []
            for k, val in props.items():
                safe_key = _safe_param(k)
                safe_prop = _safe_prop(k)
                props_parts.append(f"{safe_prop}: ${safe_key}")
                safe_props[safe_key] = val
            props_str = ", ".join(props_parts) if props_parts else ""

            if props_str:
                await self.graph.run_query(f"""
                    MATCH (a {{name: $source}})
                    MATCH (b {{name: $target}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r += {{ {props_str} }}
                """, {"source": source, "target": target, **safe_props})
            else:
                await self.graph.run_query(f"""
                    MATCH (a {{name: $source}})
                    MATCH (b {{name: $target}})
                    MERGE (a)-[r:{rel_type}]->(b)
                """, {"source": source, "target": target})

        logger.info(
            "Graph updated: paper=%s, %d entities, %d relationships",
            paper_id, len(entities), len(relationships),
        )

    async def get_paper_count(self) -> int:
        """统计图谱中论文节点数"""
        result = await self.graph.run_query(
            "MATCH (p:Paper) RETURN count(p) AS count"
        )
        return result[0]["count"] if result else 0

    async def get_entity_count(self) -> dict[str, int]:
        """统计各类实体数量"""
        counts = {}
        for label in [METHOD, DATASET, ARCHITECTURE, METRIC, CONCEPT]:
            result = await self.graph.run_query(
                f"MATCH (e:{label}) RETURN count(e) AS count"
            )
            counts[label] = result[0]["count"] if result else 0
        return counts
