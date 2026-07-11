"""
科研助手工具集 — 论文摄入、多源搜索、知识图谱、实验跟踪

在 Agent 启动时异步初始化数据库连接、注册科研工具。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from agent.config_models import Config
from agent.tools.registry import ToolRegistry
from bootstrap.toolsets.protocol import (
    ToolsetDeps,
    ToolsetProvider,
    build_registration_result,
)

logger = logging.getLogger(__name__)


class ResearchToolsetProvider(ToolsetProvider):
    """
    注册论文摄入、搜索、知识图谱、实验跟踪等科研工具。

    register() 是同步的，只检查配置并存储依赖。
    实际的异步初始化（数据库连接等）由 init_async() 完成，
    需在 CoreRuntime.start() 中调用。
    """

    def __init__(self):
        self._deps: ToolsetDeps | None = None
        self._registry: ToolRegistry | None = None
        self._tools_registered = False

    def register(
        self,
        registry: ToolRegistry,
        deps: ToolsetDeps,
    ):
        config: Config | None = deps.config
        if config is None or not config.research.enabled:
            logger.info("Research tools disabled (research.enabled=false)")
            return build_registration_result(registry=registry, source_name="research", before=set())

        self._deps = deps
        self._registry = registry
        logger.info("Research toolset configured — async init pending")

        return build_registration_result(registry=registry, source_name="research", before=set())

    async def init_async(self) -> None:
        """异步初始化数据库连接、管道、检索器，并注册工具。"""
        if self._tools_registered:
            return
        self._tools_registered = True

        deps = self._deps
        registry = self._registry
        if deps is None or registry is None:
            logger.warning("ResearchToolsetProvider not configured (register not called)")
            return

        config = deps.config
        if config is None:
            return
        cfg = config.research
        workspace: Path = deps.workspace
        provider = deps.provider

        # ── ① PostgreSQL ─────────────────────────────────────────────
        from research.db import ResearchDatabase

        db = ResearchDatabase(cfg.database)
        ok = await db.verify_connectivity()
        if not ok:
            logger.warning(
                "PostgreSQL not reachable at %s:%s — research tools disabled. "
                "Run: docker compose -f docker/docker-compose.research.yml up -d",
                cfg.database.host, cfg.database.port,
            )
            return

        await db.init_tables()
        await db.ensure_vector_columns()
        logger.info("PostgreSQL connected and tables ready")

        # ── ② Neo4j ──────────────────────────────────────────────────
        from research.graph.driver import ResearchGraph

        graph = ResearchGraph(cfg.graph)
        graph_ok = await graph.verify_connectivity()
        graphrag = None
        if graph_ok:
            from research.graph.writer import GraphWriter
            writer = GraphWriter(graph)
            await writer.init_schema()
            logger.info("Neo4j connected and schema ready")
        else:
            logger.warning("Neo4j not reachable — graph features disabled")

        # ── ③ Embedding ────────────────────────────────────────────
        from research.ingestion.pipeline import EmbeddingService

        embedder = EmbeddingService(
            model=cfg.embedding.model,
            dim=cfg.embedding.dimension,
            base_url=cfg.embedding.base_url or None,
            api_key=cfg.embedding.api_key or None,
            provider=provider,
        )

        # ── ④ IngestionPipeline ──────────────────────────────────────
        from research.ingestion.pipeline import IngestionPipeline

        def _on_paper_indexed(paper_id: str):
            if not graph:
                return
            try:
                from research.graph.extractor import GraphExtractor
                from research.graph.writer import GraphWriter
                from sqlalchemy import text

                async def _build_graph():
                    try:
                        paper = await db.fetch_one(
                            text("SELECT id, title, abstract FROM papers WHERE id=:pid"),
                            {"pid": paper_id},
                        )
                        if paper:
                            extractor = GraphExtractor(provider)
                            entities = await extractor.extract(paper.title, paper.abstract)
                            if entities:
                                await GraphWriter(graph).write_entities(paper_id, entities)
                                logger.info("Graph built for paper %s", paper_id)
                    except Exception as e:
                        logger.warning("Graph build failed for %s: %s", paper_id, e)

                asyncio.ensure_future(_build_graph())
            except Exception as e:
                logger.warning("Failed to schedule graph building: %s", e)

        pipeline = IngestionPipeline(
            db=db,
            embedder=embedder,
            storage_dir=workspace / "papers",
            chunk_size=cfg.parsing.chunk_size,
            chunk_overlap=cfg.parsing.chunk_overlap,
            on_indexed=_on_paper_indexed,
            llm_provider=provider,
        )

        # ── ⑤ Retrievers ────────────────────────────────────────────
        from research.retrieval.vector import VectorRetriever
        from research.retrieval.keyword import KeywordRetriever
        from research.retrieval.fusion import RRFFusion

        vector_retriever = VectorRetriever(db)
        keyword_retriever = KeywordRetriever(db)
        fusion = RRFFusion()
        if graph_ok:
            from research.retrieval.graphrag import GraphRAGRetriever
            graphrag = GraphRAGRetriever(graph)

        # ── ⑥ PaperSearcher ──────────────────────────────────────────
        paper_searcher = None
        try:
            from research.search.fusion import PaperSearcher
            paper_searcher = PaperSearcher()
            logger.info("PaperSearcher initialized with 4 sources")
        except Exception as e:
            logger.warning("PaperSearcher init failed: %s", e)

        # ── ⑦ Register tools ────────────────────────────────────────
        from research.tools.research_tools import (
            IngestPaperTool, SearchPapersTool, QueryGraphTool,
            PaperDetailTool, CodeLookupTool, SummarizePaperTool, LatexFormatTool,
        )
        from research.tools.experiment_tools import (
            CreateExperimentTool, TrackALRoundTool, CompareExperimentsTool,
        )

        registry.register(
            IngestPaperTool(pipeline=pipeline, db=db),
            risk="read-only",
            search_hint="导入论文 添加文献 摄入 arxiv PDF 论文入库",
        )
        registry.register(
            SearchPapersTool(
                vector_retriever=vector_retriever,
                keyword_retriever=keyword_retriever,
                graphrag_retriever=graphrag,
                embedder=embedder,
                fusion=fusion,
                web_searcher=paper_searcher,
            ),
            risk="read-only",
            search_hint="论文搜索 文献查询 找论文 检索论文 方法搜索 论文检索",
        )
        if graphrag:
            registry.register(
                QueryGraphTool(graphrag=graphrag),
                risk="read-only",
                search_hint="知识图谱 方法对比 实体关系 neo4j 图谱查询 方法关系",
            )
        registry.register(CreateExperimentTool(db=db), risk="write")
        registry.register(TrackALRoundTool(db=db), risk="write")
        registry.register(CompareExperimentsTool(db=db), risk="read-only")
        registry.register(PaperDetailTool(), risk="read-only")
        registry.register(CodeLookupTool(), risk="read-only")
        registry.register(
            SummarizePaperTool(llm_provider=provider, pipeline=pipeline),
            risk="read-only",
        )
        registry.register(LatexFormatTool(), risk="read-only")

        logger.info("Research tools registered successfully")
