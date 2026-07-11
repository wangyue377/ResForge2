"""
科研 Dashboard API 路由

提供论文管理、实验跟踪、知识图谱统计等接口。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import text

from research.db import ResearchDatabase
from research.graph.driver import ResearchGraph

logger = logging.getLogger(__name__)


def register_research_routes(
    app: FastAPI,
    db: Optional[ResearchDatabase] = None,
    graph: Optional[ResearchGraph] = None,
):
    """注册科研 Dashboard 路由到 FastAPI 应用"""

    # ── 论文统计 ─────────────────────────────────────────────

    @app.get("/api/dashboard/research/papers/overview")
    async def research_papers_overview() -> dict[str, Any]:
        if not db:
            raise HTTPException(status_code=503, detail="科研数据库未连接")
        async with db.get_session() as session:
            total = (await session.execute(
                text("SELECT count(*) FROM papers")
            )).scalar() or 0
            indexed = (await session.execute(
                text("SELECT count(*) FROM papers WHERE status='indexed'")
            )).scalar() or 0
            chunk_total = (await session.execute(
                text("SELECT count(*) FROM paper_chunks")
            )).scalar() or 0
            recent = (await session.execute(
                text("""
                    SELECT title, arxiv_id, created_at, status
                    FROM papers ORDER BY created_at DESC LIMIT 5
                """)
            )).fetchall()

        return {
            "total_papers": total,
            "indexed_papers": indexed,
            "total_chunks": chunk_total,
            "latest_papers": [
                {"title": r[0][:80], "arxiv_id": r[1], "created_at": str(r[2]), "status": r[3]}
                for r in recent
            ],
        }

    @app.get("/api/dashboard/research/papers")
    async def list_papers(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        if not db:
            raise HTTPException(status_code=503, detail="科研数据库未连接")

        allowed_sort = {"created_at", "title", "published_date", "status"}
        if sort_by not in allowed_sort:
            sort_by = "created_at"
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"

        offset = (page - 1) * page_size
        conditions = ""
        params: dict[str, Any] = {"limit": page_size, "offset": offset}
        if q:
            conditions = "WHERE p.title ILIKE :q OR p.abstract ILIKE :q"
            params["q"] = f"%{q}%"

        async with db.get_session() as session:
            total = (await session.execute(
                text(f"SELECT count(*) FROM papers p {conditions}"), params
            )).scalar() or 0
            rows = (await session.execute(
                text(f"""
                    SELECT p.id, p.title, p.arxiv_id, p.authors, p.published_date,
                           p.journal, p.status, p.created_at,
                           (SELECT count(*) FROM paper_chunks WHERE paper_id=p.id) AS chunk_count
                    FROM papers p {conditions}
                    ORDER BY p.{sort_by} {sort_order}
                    LIMIT :limit OFFSET :offset
                """),
                params,
            )).fetchall()

        return {
            "items": [
                {
                    "id": str(r[0]),
                    "title": r[1] or "",
                    "arxiv_id": r[2] or "",
                    "authors": r[3] or [],
                    "published_date": str(r[4]) if r[4] else "",
                    "journal": r[5] or "",
                    "status": r[6] or "",
                    "created_at": str(r[7]),
                    "chunk_count": r[8] or 0,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @app.get("/api/dashboard/research/papers/{paper_id}")
    async def get_paper_detail(paper_id: str) -> dict[str, Any]:
        if not db:
            raise HTTPException(status_code=503, detail="科研数据库未连接")
        async with db.get_session() as session:
            row = (await session.execute(
                text("""
                    SELECT id, title, arxiv_id, authors, abstract, published_date,
                           journal, paper_url, code_url, keywords, research_area, status, created_at
                    FROM papers WHERE id=:pid
                """),
                {"pid": paper_id},
            )).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="论文不存在")

            chunks = (await session.execute(
                text("""
                    SELECT chunk_index, section, content[:500] AS content_preview, token_count
                    FROM paper_chunks WHERE paper_id=:pid ORDER BY chunk_index LIMIT 50
                """),
                {"pid": paper_id},
            )).fetchall()

        return {
            "id": str(row[0]),
            "title": row[1] or "",
            "arxiv_id": row[2] or "",
            "authors": row[3] or [],
            "abstract": row[4] or "",
            "published_date": str(row[5]) if row[5] else "",
            "journal": row[6] or "",
            "paper_url": row[7] or "",
            "code_url": row[8] or "",
            "keywords": row[9] or [],
            "research_area": row[10] or [],
            "status": row[11] or "",
            "created_at": str(row[12]),
            "chunks": [
                {"index": c[0], "section": c[1], "content_preview": c[2], "tokens": c[3]}
                for c in chunks
            ],
        }

    # ── 实验跟踪统计 ─────────────────────────────────────────

    @app.get("/api/dashboard/research/experiments")
    async def list_experiments(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> dict[str, Any]:
        if not db:
            raise HTTPException(status_code=503, detail="科研数据库未连接")
        offset = (page - 1) * page_size
        async with db.get_session() as session:
            total = (await session.execute(
                text("SELECT count(*) FROM experiments")
            )).scalar() or 0
            rows = (await session.execute(
                text("""
                    SELECT e.id, e.name, e.status, e.config, e.started_at, e.created_at,
                           (SELECT count(*) FROM active_learning_rounds WHERE experiment_id=e.id) AS al_rounds
                    FROM experiments e
                    ORDER BY e.created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": page_size, "offset": offset},
            )).fetchall()

        return {
            "items": [
                {
                    "id": str(r[0]),
                    "name": r[1] or "",
                    "status": r[2] or "",
                    "config_summary": _config_summary(r[3]),
                    "started_at": str(r[4]) if r[4] else "",
                    "created_at": str(r[5]),
                    "al_rounds": r[6] or 0,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @app.get("/api/dashboard/research/experiments/{experiment_id}/rounds")
    async def get_experiment_rounds(experiment_id: str) -> list[dict[str, Any]]:
        if not db:
            raise HTTPException(status_code=503, detail="科研数据库未连接")
        async with db.get_session() as session:
            rows = (await session.execute(
                text("""
                    SELECT round_number, sampling_strategy, queried_count, metrics, queried_at
                    FROM active_learning_rounds
                    WHERE experiment_id=:eid
                    ORDER BY round_number
                """),
                {"eid": experiment_id},
            )).fetchall()
        return [
            {
                "round": r[0],
                "strategy": r[1] or "",
                "queried": r[2] or 0,
                "metrics": r[3] if isinstance(r[3], dict) else {},
                "queried_at": str(r[4]),
            }
            for r in rows
        ]

    # ── 知识图谱统计 ─────────────────────────────────────────

    @app.get("/api/dashboard/research/graph/overview")
    async def graph_overview() -> dict[str, Any]:
        if not graph:
            raise HTTPException(status_code=503, detail="图数据库未连接")
        try:
            paper_count = (await graph.run_query(
                "MATCH (p:Paper) RETURN count(p) AS count"
            ))[0]["count"]
            method_count = (await graph.run_query(
                "MATCH (m:Method) RETURN count(m) AS count"
            ))[0]["count"]
            dataset_count = (await graph.run_query(
                "MATCH (d:Dataset) RETURN count(d) AS count"
            ))[0]["count"]
            concept_count = (await graph.run_query(
                "MATCH (c:Concept) RETURN count(c) AS count"
            ))[0]["count"]
            rel_count = (await graph.run_query(
                "MATCH ()-[r]->() RETURN count(r) AS count"
            ))[0]["count"]

            top_methods = await graph.run_query("""
                MATCH (m:Method)
                OPTIONAL MATCH (m)<-[:PROPOSES]-(p:Paper)
                RETURN m.name AS method, count(p) AS paper_count
                ORDER BY paper_count DESC LIMIT 10
            """)
            top_datasets = await graph.run_query("""
                MATCH (d:Dataset)
                OPTIONAL MATCH (d)<-[:USES]-()
                RETURN d.name AS dataset, count(*) AS ref_count
                ORDER BY ref_count DESC LIMIT 10
            """)

            return {
                "paper_count": paper_count,
                "method_count": method_count,
                "dataset_count": dataset_count,
                "concept_count": concept_count,
                "relationship_count": rel_count,
                "top_methods": [
                    {"name": r["method"], "papers": r["paper_count"]} for r in top_methods
                ],
                "top_datasets": [
                    {"name": r["dataset"], "references": r["ref_count"]} for r in top_datasets
                ],
            }
        except Exception as e:
            logger.warning("Graph overview failed: %s", e)
            return {
                "paper_count": 0, "method_count": 0, "dataset_count": 0,
                "concept_count": 0, "relationship_count": 0,
                "top_methods": [], "top_datasets": [],
                "error": str(e),
            }

    # ── 搜索统计 ─────────────────────────────────────────────

    @app.get("/api/dashboard/research/stats")
    async def research_stats() -> dict[str, Any]:
        """综合统计"""
        stats = {"database": False, "graph": False}
        if db:
            try:
                async with db.get_session() as session:
                    stats["database"] = True
                    stats["papers"] = (await session.execute(
                        text("SELECT count(*) FROM papers")
                    )).scalar() or 0
                    stats["chunks"] = (await session.execute(
                        text("SELECT count(*) FROM paper_chunks")
                    )).scalar() or 0
                    stats["experiments"] = (await session.execute(
                        text("SELECT count(*) FROM experiments")
                    )).scalar() or 0
                    stats["al_rounds"] = (await session.execute(
                        text("SELECT count(*) FROM active_learning_rounds")
                    )).scalar() or 0
            except Exception:
                stats["database"] = False
        if graph:
            try:
                stats["graph"] = True
                result = await graph.run_query(
                    "MATCH (e) RETURN count(e) AS count"
                )
                stats["graph_entities"] = result[0]["count"] if result else 0
            except Exception:
                stats["graph"] = False
        return stats


def _config_summary(config_raw: Any) -> str:
    """从实验配置 JSON 中提取摘要"""
    if not config_raw:
        return ""
    try:
        cfg = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
        parts = []
        for key in ("model", "dataset", "ssl_method", "al_strategy", "backbone"):
            if key in cfg:
                parts.append(f"{key}={cfg[key]}")
        return ", ".join(parts) if parts else str(cfg)[:80]
    except (json.JSONDecodeError, TypeError):
        return str(config_raw)[:80]
