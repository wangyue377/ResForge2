"""
ArXiv API 加载器

通过 arxiv.py 库获取论文元数据和 PDF 下载。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import arxiv
import httpx

logger = logging.getLogger(__name__)

# ArXiv ID 正则
ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


class ArxivLoader:
    """ArXiv API 论文信息获取与 PDF 下载"""

    def __init__(self, storage_dir: str | Path = "~/.akashic/workspace/papers"):
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.client = arxiv.Client(

        )

    @staticmethod
    def extract_arxiv_id(source: str) -> str:
        """从 URL 或 ID 字符串中提取 ArXiv ID"""
        match = ARXIV_ID_PATTERN.search(source)
        if match:
            return match.group(1)
        raise ValueError(f"无法从 {source!r} 提取 ArXiv ID")

    async def fetch_by_id(self, arxiv_id: str) -> dict:
        """
        通过 ArXiv ID 获取论文元数据。

        Returns:
            {arxiv_id, title, authors, abstract, published_date, paper_url, pdf_url}
        """
        search = arxiv.Search(id_list=[arxiv_id])
        results = [r async for r in self.client.results(search)]
        if not results:
            raise ValueError(f"ArXiv ID 未找到: {arxiv_id}")
        return self._result_to_dict(results[0])

    async def search(
        self, query: str, max_results: int = 10, sort_by: str = "relevance"
    ) -> list[dict]:
        """
        搜索 ArXiv 论文。

        Args:
            query: 搜索关键词
            max_results: 最大返回数
            sort_by: relevance / lastUpdatedDate / submittedDate

        Returns:
            论文元数据列表
        """
        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "updated": arxiv.SortCriterion.LastUpdatedDate,
            "submitted": arxiv.SortCriterion.SubmittedDate,
        }
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_map.get(sort_by, arxiv.SortCriterion.Relevance),
        )
        results = []
        async for r in self.client.results(search):
            results.append(self._result_to_dict(r))
        return results

    async def download_pdf(self, pdf_url: str, arxiv_id: str) -> str:
        """
        下载 PDF 到本地存储。

        Returns:
            本地文件路径
        """
        pdf_path = self.storage_dir / f"{arxiv_id}.pdf"
        if pdf_path.exists():
            logger.info("PDF already exists: %s", pdf_path)
            return str(pdf_path)

        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            pdf_path.write_bytes(response.content)

        logger.info("Downloaded PDF: %s (%d KB)", pdf_path, pdf_path.stat().st_size // 1024)
        return str(pdf_path)

    def _result_to_dict(self, result: arxiv.Result) -> dict:
        return {
            "arxiv_id": self.extract_arxiv_id(result.entry_id),
            "title": result.title,
            "authors": [a.name for a in result.authors],
            "abstract": result.summary,
            "published_date": result.published.date(),
            "paper_url": result.entry_id,
            "pdf_url": result.pdf_url,
            "comment": result.comment or "",
            "journal_ref": result.journal_ref or "",
            "primary_category": result.primary_category,
            "categories": result.categories,
        }
