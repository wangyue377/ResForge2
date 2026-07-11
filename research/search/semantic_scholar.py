"""
Semantic Scholar API 论文搜索

API 文档: https://api.semanticscholar.org/api-docs/
免费额度: 100 req/min（无需 API key），有 key 可提至 1000 req/min
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from research.search import PaperResult, PaperSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"

# 需要从返回中提取的字段
FIELDS = "title,authors,abstract,externalIds,url,publicationDate,citationCount,venue,publicationVenue"


class SemanticScholarSource(PaperSource):
    """Semantic Scholar API 搜索源"""

    name = "semantic_scholar"

    def __init__(self, api_key: str = "", timeout: float = 15.0):
        self.api_key = api_key
        self.timeout = timeout

    async def search(
        self,
        query: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperResult]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        params: dict[str, Any] = {
            "query": query,
            "limit": min(top_k, 50),
            "fields": FIELDS,
        }
        if year_from and year_to:
            params["year"] = f"{year_from}-{year_to}"
        elif year_from:
            params["year"] = f"{year_from}-"

        # 最多重试 2 次（应对 429 限流 + 网络抖动）
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(
                        f"{BASE_URL}/paper/search",
                        params=params,
                        headers=headers,
                    )
                    if resp.status_code == 429:
                        wait = 3 * (attempt + 1)
                        logger.warning("Semantic Scholar rate limited (429), retrying in %ds", wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < 2:
                    logger.warning("Semantic Scholar connection error, retry %d: %s", attempt + 1, e)
                    await asyncio.sleep(1)
                    continue
                logger.warning("Semantic Scholar search failed after retries: %s", e)
                return []
            except Exception as e:
                logger.warning("Semantic Scholar search failed: %s", e)
                return []
        else:
            logger.warning("Semantic Scholar exhausted retries")
            return []

        results = []
        for paper in data.get("data", []):
            try:
                ext_ids = paper.get("externalIds") or {}
                results.append(self._to_result(paper, ext_ids))
            except Exception as e:
                logger.debug("Skip SS result: %s", e)
        return results

    def _to_result(self, paper: dict, ext_ids: dict) -> PaperResult:
        authors = [
            a.get("name", "") for a in (paper.get("authors") or [])
        ]
        return PaperResult(
            source=self.name,
            title=paper.get("title", ""),
            authors=authors,
            abstract=paper.get("abstract") or "",
            url=paper.get("url") or "",
            arxiv_id=ext_ids.get("ArXiv", ""),
            published_date=paper.get("publicationDate") or "",
            citation_count=paper.get("citationCount") or 0,
            venues=[paper.get("venue", "")] if paper.get("venue") else [],
        )
