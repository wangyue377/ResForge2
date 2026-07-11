"""
科研助手插件 — 注册到 Akashic Agent

在 Agent 启动时自动初始化数据库连接、注册工具。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.config_models import ResearchConfig
from agent.plugins import Plugin


logger = logging.getLogger(__name__)


class ResearchPlugin(Plugin):
    """
    科研助手插件

    功能：
    - 管理 PostgreSQL 数据库连接（papers + chunks + experiments）
    - 管理 Neo4j 图数据库连接（知识图谱）
    - 提供 Embedding 服务
    - 注册论文摄入、搜索、图谱查询、实验跟踪等工具
    - 触发后台知识图谱构建
    - 自动检测用户研究意图，注入相关论文上下文
    """

    name = "research"

    def __init__(self, context: Any = None):
        super().__init__()
        self.context = context
        self.config: ResearchConfig | None = None
        self.db = None
        self.graph = None
        self.embedder = None
        self.pipeline = None
        self._intent_detector = None
        self._tools_registered = False

    def is_active(self) -> bool:
        """插件是否启用，由 config.research.enabled 控制"""
        if not self.context or not hasattr(self.context, "config"):
            return False
        cfg = getattr(self.context.config, "research", None)
        return bool(cfg and cfg.enabled)

    async def initialize(self):
        """Agent 启动时初始化"""
        if not self.is_active():
            logger.info("ResearchPlugin disabled (research.enabled=false)")
            return

        cfg = self.context.config.research
        self.config = cfg
        logger.info("Initializing ResearchPlugin...")

        # ① 初始化数据库
        from research.db import ResearchDatabase
        self.db = ResearchDatabase(cfg.database)
        ok = await self.db.verify_connectivity()
        if not ok:
            logger.warning(
                "PostgreSQL not reachable at %s:%s — research features disabled. "
                "Run: docker compose -f docker/docker-compose.research.yml up -d",
                cfg.database.host, cfg.database.port,
            )
            return
        await self.db.init_tables()
        await self.db.ensure_vector_columns()
        logger.info("PostgreSQL connected and tables ready")

        # ② 初始化图数据库
        from research.graph.driver import ResearchGraph
        self.graph = ResearchGraph(cfg.graph)
        graph_ok = await self.graph.verify_connectivity()
        if graph_ok:
            from research.graph.writer import GraphWriter
            writer = GraphWriter(self.graph)
            await writer.init_schema()
            logger.info("Neo4j connected and schema ready")
        else:
            logger.warning("Neo4j not reachable — graph features disabled")

        # ③ 初始化嵌入服务
        from research.ingestion.pipeline import EmbeddingService
        self.embedder = EmbeddingService(
            model=cfg.embedding.model,
            dim=cfg.embedding.dimension,
            base_url=cfg.embedding.base_url or None,
            api_key=cfg.embedding.api_key or None,
            provider=self.context.provider,
        )

        # ④ 初始化摄入管道
        from research.ingestion.pipeline import IngestionPipeline
        self.pipeline = IngestionPipeline(
            db=self.db,
            embedder=self.embedder,
            storage_dir=Path(self.context.workspace) / "papers",
            chunk_size=cfg.parsing.chunk_size,
            chunk_overlap=cfg.parsing.chunk_overlap,
            on_indexed=self._on_paper_indexed,
            llm_provider=self.context.provider,
        )

        # ⑤ 初始化检索器
        from research.retrieval.vector import VectorRetriever
        from research.retrieval.keyword import KeywordRetriever
        from research.retrieval.fusion import RRFFusion
        self.vector_retriever = VectorRetriever(self.db)
        self.keyword_retriever = KeywordRetriever(self.db)
        self.fusion = RRFFusion()
        self.graphrag = None
        if graph_ok:
            from research.retrieval.graphrag import GraphRAGRetriever
            self.graphrag = GraphRAGRetriever(self.graph)

        # ⑥ 初始化意图检测器
        from research.intent.detector import IntentDetector
        self._intent_detector = IntentDetector(
            getattr(self.context, "fast_provider", self.context.provider)
        )

        # ⑦ 配置 ArXiv MCP 推送源（如果开启了 ArXiv 监控）
        if cfg.arxiv.enabled:
            try:
                from research.proactive.setup_arxiv_source import ensure_arxiv_mcp_config
                ensure_arxiv_mcp_config(Path(self.context.workspace))
                logger.info("ArXiv MCP source configured for proactive push")
            except Exception as e:
                logger.warning("ArXiv MCP setup failed: %s", e)

        # ⑧ 初始化多源搜索器
        try:
            from research.search.fusion import PaperSearcher
            self.paper_searcher = PaperSearcher()
            logger.info("PaperSearcher initialized with 4 sources")
        except Exception as e:
            logger.warning("PaperSearcher init failed (search.web will be unavailable): %s", e)
            self.paper_searcher = None

        # ⑨ 注册工具
        self._register_tools()

        logger.info("ResearchPlugin initialized successfully")

    def _register_tools(self):
        """注册所有科研工具到 Agent"""
        if self._tools_registered:
            return

        from research.tools.research_tools import (
            IngestPaperTool,
            SearchPapersTool,
            QueryGraphTool,
            PaperDetailTool,
            CodeLookupTool,
            SummarizePaperTool,
            LatexFormatTool,
        )
        from research.tools.experiment_tools import (
            CreateExperimentTool,
            TrackALRoundTool,
            CompareExperimentsTool,
        )

        registry = self.context.tool_registry

        registry.register(
            IngestPaperTool(pipeline=self.pipeline, db=self.db),
            risk="read-only",
            search_hint="导入论文 添加文献 摄入 arxiv PDF 论文入库",
        )
        registry.register(
            SearchPapersTool(
                vector_retriever=self.vector_retriever,
                keyword_retriever=self.keyword_retriever,
                graphrag_retriever=self.graphrag,
                embedder=self.embedder,
                fusion=self.fusion,
                web_searcher=getattr(self, "paper_searcher", None),
            ),
            risk="read-only",
            search_hint="论文搜索 文献查询 找论文 检索论文 方法搜索 论文检索",
        )
        if self.graphrag:
            registry.register(
                QueryGraphTool(graphrag=self.graphrag),
                risk="read-only",
                search_hint="知识图谱 方法对比 实体关系 neo4j 图谱查询 方法关系",
            )
        registry.register(CreateExperimentTool(db=self.db))
        registry.register(TrackALRoundTool(db=self.db))
        registry.register(CompareExperimentsTool(db=self.db))
        registry.register(PaperDetailTool())
        registry.register(CodeLookupTool())
        registry.register(SummarizePaperTool(
            llm_provider=self.context.provider,
            pipeline=self.pipeline,
        ))
        registry.register(LatexFormatTool())

        self._tools_registered = True
        logger.info("Research tools registered (4 new tools added)")

    def before_reasoning_modules(self) -> list[object]:
        """注册意图检测模块（BeforeReasoning 阶段）"""
        if not self._intent_detector:
            return []
        from research.plugin.intent_module import ResearchContextModule
        return [ResearchContextModule(self)]

    def prompt_render_modules(self) -> list[object]:
        """注册上下文注入模块（PromptRender 阶段）"""
        if not self._intent_detector:
            return []
        from research.plugin.intent_module import ResearchPromptInjectModule
        return [ResearchPromptInjectModule(self)]

    def _on_paper_indexed(self, paper_id: str):
        """论文索引完成后的回调——触发后台知识图谱构建"""
        if not self.graph:
            return
        try:
            from research.graph.extractor import GraphExtractor
            from research.graph.writer import GraphWriter
            from sqlalchemy import text

            # 在后台任务中执行（不阻塞返回）
            import asyncio
            asyncio.ensure_future(self._build_graph_for_paper(paper_id))
        except Exception as e:
            logger.warning("Failed to schedule graph building: %s", e)

    async def _build_graph_for_paper(self, paper_id: str):
        """后台构建单篇论文的知识图谱"""
        try:
            from research.graph.extractor import GraphExtractor
            from research.graph.writer import GraphWriter

            # 获取论文信息
            async with self.db.get_session() as session:
                from sqlalchemy import text
                paper = (await session.execute(
                    text("SELECT id, title, arxiv_id FROM papers WHERE id=:pid"),
                    {"pid": paper_id},
                )).fetchone()
                if not paper:
                    return

                chunks = (await session.execute(
                    text("SELECT chunk_index, content, section FROM paper_chunks WHERE paper_id=:pid ORDER BY chunk_index"),
                    {"pid": paper_id},
                )).fetchall()

            # LLM 提取实体关系（用主模型确保提取质量）
            extractor = GraphExtractor(self.context.provider)
            result = await extractor.extract_batch(
                title=paper[1],
                chunks=[{"chunk_index": c[0], "content": c[1], "section": c[2]} for c in chunks],
                max_chunks=5,
            )

            if result["entities"] or result["relationships"]:
                writer = GraphWriter(self.graph)
                await writer.write_paper_entities(
                    paper_id=paper[2] or paper[0],
                    title=paper[1],
                    entities=result["entities"],
                    relationships=result["relationships"],
                )
                logger.info(
                    "Graph built for paper %s: %d entities, %d relationships",
                    paper_id, len(result["entities"]), len(result["relationships"]),
                )
        except Exception as e:
            logger.warning("Graph building failed for paper %s: %s", paper_id, e)

    async def terminate(self):
        """Agent 关闭时清理连接"""
        if self.db:
            await self.db.close()
        if self.graph:
            await self.graph.close()
        logger.info("ResearchPlugin shut down")
