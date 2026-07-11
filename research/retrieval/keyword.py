"""
PostgreSQL 全文搜索 (BM25) 检索
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from research.db import ResearchDatabase

logger = logging.getLogger(__name__)


class KeywordRetriever:
    """基于 PostgreSQL 全文搜索的 BM25 检索"""

    def __init__(self, db: ResearchDatabase):
        self.db = db

    async def search_chunks(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        在 paper_chunks 表上进行关键词全文搜索。

        Args:
            query: 搜索关键词（英文）
            top_k: 返回结果数

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
                    ts_rank(
                        to_tsvector('english', pc.content),
                        plainto_tsquery('english', :query)
                    ) AS score
                FROM paper_chunks pc
                JOIN papers p ON p.id = pc.paper_id
                WHERE to_tsvector('english', pc.content) @@ plainto_tsquery('english', :query)
                ORDER BY score DESC
                LIMIT :top_k
            """)
            result = await session.execute(sql, {"query": query, "top_k": top_k})
            rows = [dict(row._mapping) for row in result]
            for r in rows:
                r["score"] = round(float(r["score"]), 4)
            return rows

    async def search_papers(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        在 papers 表级别进行关键词搜索。

        Returns:
            [{id, title, arxiv_id, abstract_preview, score}, ...]
        """
        async with self.db.get_session() as session:
            sql = text("""
                SELECT
                    id, title, arxiv_id,
                    left(abstract, 300) AS abstract_preview,
                    ts_rank(
                        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, '')),
                        plainto_tsquery('english', :query)
                    ) AS score
                FROM papers
                WHERE to_tsvector('english',
                    coalesce(title, '') || ' ' || coalesce(abstract, '')
                ) @@ plainto_tsquery('english', :query)
                ORDER BY score DESC
                LIMIT :top_k
            """)
            result = await session.execute(sql, {"query": query, "top_k": top_k})
            rows = [dict(row._mapping) for row in result]
            for r in rows:
                r["score"] = round(float(r["score"]), 4)
            return rows
