"""
论文摄入管道编排

端到端串联：ArXiv/PDF → 解析 → 分块 → 嵌入 → 存储 → 触发图谱构建
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import text

from research.db import ResearchDatabase
from research.ingestion.arxiv_loader import ArxivLoader
from research.ingestion.chunker import PaperChunker
from research.ingestion.doc_parser import DocumentParser
from research.ingestion.metadata import MetadataExtractor
from research.ingestion.pdf_parser import PDFParser
from research.models.paper import Paper, PaperChunk

logger = logging.getLogger(__name__)


class EmbeddingService:
    """向量化服务——调用 OpenAI 兼容的嵌入接口（本地或云端均可）"""

    def __init__(
        self,
        model: str = "text-embedding-v3",
        dim: int = 1024,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: Any | None = None,
    ):
        """
        Args:
            model: 嵌入模型名
            dim: 向量维度
            base_url: OpenAI 兼容嵌入端点（dashscope / 本地 vLLM 等）
            api_key: 嵌入服务 API key
            provider: 兜底——当未配置 base_url/api_key 时复用 LLM provider
        """
        self.model = model
        self.dim = dim
        if base_url and api_key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self._mode = "client"
        elif provider is not None:
            self._provider = provider
            self._mode = "provider"
        else:
            raise ValueError("EmbeddingService 需要 base_url+api_key 或 provider")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本（自动分批，每批最多 10 条）"""
        batch_size = 10
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            if self._mode == "client":
                response = await self._client.embeddings.create(model=self.model, input=batch, encoding_format="float")
                all_embeddings.extend(item.embedding for item in response.data)
            else:
                response = await self._provider.embed(model=self.model, input=batch)
                all_embeddings.extend(item["embedding"] for item in response["data"])
        return all_embeddings

    async def embed_text(self, text: str) -> list[float]:
        result = await self.embed_texts([text])
        return result[0]


class IngestionPipeline:
    """
    论文摄入管道。

    流程:
    source (ArXiv ID / PDF path)
      → ① 获取元数据
      → ② 下载 PDF（如需要）
      → ③ 提取全文文本
      → ④ 语义分块
      → ⑤ 批量向量化
      → ⑥ 存入 PostgreSQL (papers + paper_chunks)
      → ⑦ 触发后台图谱构建事件
    """

    def __init__(
        self,
        db: ResearchDatabase,
        embedder: EmbeddingService,
        storage_dir: str | Path = "~/.akashic/workspace/papers",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        on_indexed: Optional[Callable[[str], None]] = None,
        llm_provider: Optional[Any] = None,
    ):
        """
        Args:
            db: PostgreSQL 数据库管理器
            embedder: 向量化服务
            storage_dir: PDF 下载目录
            chunk_size: 分块大小（单词数）
            chunk_overlap: 分块重叠（单词数）
            on_indexed: 论文索引完成后的回调（用于触发图谱构建）
            llm_provider: 用于本地 PDF 自动提取元数据的 LLM provider
        """
        self.db = db
        self.embedder = embedder
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.on_indexed = on_indexed

        self.pdf_parser = PDFParser()
        self.doc_parser = DocumentParser()
        self.arxiv_loader = ArxivLoader(storage_dir=self.storage_dir)
        self.chunker = PaperChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.metadata_extractor = MetadataExtractor(llm_provider) if llm_provider else None

    async def ingest_from_arxiv(self, source: str) -> str:
        """
        从 ArXiv 链接或 ID 摄入论文。

        Args:
            source: ArXiv ID (如 "2401.12345") 或完整 URL

        Returns:
            paper_id (UUID 字符串)
        """
        arxiv_id = ArxivLoader.extract_arxiv_id(source)
        logger.info("Ingesting from ArXiv: %s", arxiv_id)

        # ① 获取元数据
        meta = await self.arxiv_loader.fetch_by_id(arxiv_id)

        # ② 下载 PDF
        pdf_path = await self.arxiv_loader.download_pdf(meta["pdf_url"], arxiv_id)

        # ③-⑦ 处理 PDF
        return await self._process_pdf(
            pdf_path=pdf_path,
            title=meta["title"],
            authors=meta["authors"],
            abstract=meta.get("abstract", ""),
            published_date=meta.get("published_date"),
            paper_url=meta.get("paper_url", ""),
            arxiv_id=arxiv_id,
        )

    async def ingest_from_pdf(
        self, pdf_path: str | Path, metadata: Optional[dict] = None
    ) -> str:
        """
        从本地 PDF 文件摄入论文。

        Args:
            pdf_path: PDF 文件路径
            metadata: 可选的外置元数据 {title, authors, abstract, ...}
                      不提供则尝试用 LLM 从首页提取

        Returns:
            paper_id (UUID 字符串)
        """
        pdf_path = Path(pdf_path)
        logger.info("Ingesting from PDF: %s", pdf_path.name)

        metadata = metadata or {}
        title = metadata.get("title")
        authors = metadata.get("authors", [])
        abstract = metadata.get("abstract", "")

        # 用户没提供标题 → 尝试 LLM 从首页提取
        if not title and self.metadata_extractor:
            try:
                first_page = self.pdf_parser.extract_first_page(str(pdf_path))
                if first_page.strip():
                    extracted = await self.metadata_extractor.extract(first_page)
                    title = extracted.get("title") or pdf_path.stem
                    if not authors:
                        authors = extracted.get("authors", [])
                    if not abstract:
                        abstract = extracted.get("abstract", "")
                    logger.info(
                        "LLM extracted title: %s | authors: %s",
                        title[:60], authors,
                    )
                else:
                    title = pdf_path.stem
            except Exception as e:
                logger.warning("LLM metadata extraction failed, fallback to filename: %s", e)
                title = pdf_path.stem
        elif not title:
            title = pdf_path.stem

        return await self._process_pdf(
            pdf_path=str(pdf_path),
            title=title,
            authors=authors,
            abstract=abstract,
            published_date=None,
            paper_url="",
            arxiv_id=None,
        )

    async def ingest_from_file(
        self, file_path: str | Path, metadata: Optional[dict] = None
    ) -> str:
        """
        从本地文件（任意支持格式）摄入论文。

        自动识别格式：PDF/Word/Excel/PPT/Markdown/代码等。

        Args:
            file_path: 文件路径
            metadata: 可选元数据 {title, authors, abstract, ...}

        Returns:
            paper_id (UUID 字符串)
        """
        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        logger.info("Ingesting from file: %s (type=%s)", file_path.name, ext)

        metadata = metadata or {}
        title = metadata.get("title", file_path.stem)
        authors = metadata.get("authors", [])
        abstract = metadata.get("abstract", "")

        # 提取全文文本
        try:
            full_text = self.doc_parser.parse(str(file_path))
        except ValueError as e:
            return f"❌ {e}"
        except ImportError as e:
            return f"❌ 缺少解析依赖: {e}。请安装: pip install python-docx python-pptx openpyxl"

        # 如果是 PDF 且用户没给标题 → 尝试 LLM 从首页提取
        if ext == ".pdf" and not metadata.get("title") and self.metadata_extractor:
            try:
                first_page = self.pdf_parser.extract_first_page(str(file_path))
                if first_page.strip():
                    extracted = await self.metadata_extractor.extract(first_page)
                    title = extracted.get("title") or title
                    if not authors:
                        authors = extracted.get("authors", [])
                    if not abstract:
                        abstract = extracted.get("abstract", "")
            except Exception as e:
                logger.warning("LLM metadata extraction failed: %s", e)

        # 后续流程：分块 → 向量化 → 存储
        return await self._process_text(
            full_text=full_text,
            title=title,
            authors=authors,
            abstract=abstract,
            source_path=str(file_path),
            arxiv_id=None,
        )

    async def extract_text_from_file(self, file_path: str | Path) -> str:
        """
        仅提取文件文本（不分块不存储），供 SummarizePaperTool 等工具使用。
        """
        return self.doc_parser.parse(str(file_path))

    async def _process_pdf(
        self,
        pdf_path: str,
        title: str,
        authors: list[str],
        abstract: str,
        published_date: Optional[date],
        paper_url: str,
        arxiv_id: Optional[str] = None,
    ) -> str:
        """PDF 处理（提取文本后委托 _process_text）"""
        full_text = self.pdf_parser.extract_text(pdf_path)
        return await self._process_text(
            full_text=full_text,
            title=title,
            authors=authors,
            abstract=abstract,
            source_path=pdf_path,
            published_date=published_date,
            paper_url=paper_url,
            arxiv_id=arxiv_id,
        )

    async def _process_text(
        self,
        full_text: str,
        title: str,
        authors: list[str],
        abstract: str,
        source_path: str = "",
        published_date: Optional[date] = None,
        paper_url: str = "",
        arxiv_id: Optional[str] = None,
    ) -> str:
        """文本处理核心逻辑：分块 → 嵌入 → 存储 → 触发图谱构建"""

        # ④ 语义分块
        # 清洗空字节等 PostgreSQL 不接受的字符
        full_text = full_text.replace("\x00", "")
        chunks = self.chunker.chunk_paper(full_text)

        # ⑤ 批量向量化
        texts = [c["content"] for c in chunks]
        logger.info("Embedding %d chunks...", len(texts))
        embeddings = await self.embedder.embed_texts(texts)

        # ⑥ 存入 PostgreSQL
        paper_id = str(uuid.uuid4())
        source_type = "arxiv" if arxiv_id else "file"
        async with self.db.get_session() as session:
            # 清洗空字节（PostgreSQL UTF8 不允许）
            _clean = lambda s: s.replace("\x00", "") if isinstance(s, str) else s
            await session.execute(
                text("""
                    INSERT INTO papers (id, arxiv_id, title, authors, abstract,
                                        published_date, paper_url, pdf_path, status, metadata)
                    VALUES (:id, :arxiv_id, :title, :authors, :abstract,
                            :published_date, :paper_url, :source_path, 'indexed', :metadata)
                """),
                {
                    "id": paper_id,
                    "arxiv_id": arxiv_id,
                    "title": _clean(title),
                    "authors": [_clean(a) for a in (authors or [])],
                    "abstract": _clean(abstract),
                    "published_date": published_date,
                    "paper_url": paper_url,
                    "source_path": source_path,
                    "metadata": json.dumps({"source": source_type}),
                },
            )

            for chunk, embedding in zip(chunks, embeddings):
                content = chunk["content"].replace("\x00", "")
                section = (chunk.get("section") or "").replace("\x00", "")
                await session.execute(
                    text("""
                        INSERT INTO paper_chunks
                            (id, paper_id, chunk_index, content, section, embedding)
                        VALUES (gen_random_uuid(), :paper_id, :chunk_index,
                                :content, :section, :embedding)
                    """),
                    {
                        "paper_id": paper_id,
                        "chunk_index": chunk["chunk_index"],
                        "content": content,
                        "section": section,
                        "embedding": json.dumps(embedding),
                    },
                )

        logger.info(
            "Paper indexed: %s (%s) — %d chunks, %d embeddings",
            title[:60], arxiv_id or source_path, len(chunks), len(embeddings),
        )

        # ⑦ 触发后台图谱构建
        if self.on_indexed:
            try:
                self.on_indexed(paper_id)
            except Exception as e:
                logger.warning("Post-index callback failed: %s", e)

        return paper_id
