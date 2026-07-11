"""
pgvector 向量语义检索
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from research.db import ResearchDatabase

logger = logging.getLogger(__name__)


class VectorRetriever:
    """基于 pgvector 的语义检索"""

    def __init__(self, db: ResearchDatabase):
        self.db = db

    async def search_chunks(
        self,
        embedding: list[float],
        top_k: int = 10,
        threshold: float = 0.45,
    ) -> list[dict[str, Any]]:
        """
        在 paper_chunks 表中进行向量相似度搜索。

        Args:
            embedding: 查询向量 (1024维)
            top_k: 返回结果数
            threshold: 最小相似度阈值

        Returns:
            [{id, content, section, chunk_index, paper_title, arxiv_id, score}, ...]
        """
        async with self.db.get_session() as session:
            sql = text("""
                SELECT
                    pc.id,
                    pc.content,
                    pc.section,
                    pc.chunk_index,
                    p.title AS paper_title,
                    p.arxiv_id,
                    1 - (pc.embedding <=> :embedding) AS score
                FROM paper_chunks pc
                JOIN papers p ON p.id = pc.paper_id
                WHERE pc.embedding IS NOT NULL
                  AND 1 - (pc.embedding <=> :embedding) > :threshold
                ORDER BY pc.embedding <=> :embedding
                LIMIT :top_k
            """)
            result = await session.execute(sql, {
                "embedding": json.dumps(embedding),
                "threshold": threshold,
                "top_k": top_k,
            })
            rows = [dict(row._mapping) for row in result]
            for r in rows:
                r["score"] = round(float(r["score"]), 4)
            return rows

    async def search_papers(
        self,
        embedding: list[float],
        top_k: int = 10,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        在 papers 表级别进行向量相似度搜索（论文级粗排）。

        Returns:
            [{id, title, arxiv_id, abstract, score}, ...]
        """
        async with self.db.get_session() as session:
            sql = text("""
                SELECT
                    id, title, arxiv_id,
                    left(abstract, 300) AS abstract_preview,
                    1 - (embedding <=> :embedding) AS score
                FROM papers
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> :embedding) > :threshold
                ORDER BY embedding <=> :embedding
                LIMIT :top_k
            """)
            result = await session.execute(sql, {
                "embedding": json.dumps(embedding),
                "threshold": threshold,
                "top_k": top_k,
            })
            rows = [dict(row._mapping) for row in result]
            for r in rows:
                r["score"] = round(float(r["score"]), 4)
            return rows
