"""
OpenAlex API 论文搜索

API: https://docs.openalex.org/
免费额度: 100k req/day（无需 API key），加 mailto 可提至更高
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from research.search import PaperResult, PaperSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org"


class OpenAlexSource(PaperSource):
    """OpenAlex API 搜索源"""

    name = "openalex"

    def __init__(self, mailto: str = "", timeout: float = 15.0):
        self.mailto = mailto
        self.timeout = timeout

    async def search(
        self,
        query: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperResult]:
        params: dict[str, Any] = {
            "search": query,
            "per_page": min(top_k, 200),
            "sort": "relevance_score:desc",
        }
        if year_from or year_to:
            parts = []
            if year_from:
                parts.append(f"from_publication_date:{year_from}-01-01")
            if year_to:
                parts.append(f"to_publication_date:{year_to}-12-31")
            params["filter"] = ",".join(parts)
        if self.mailto:
            params["mailto"] = self.mailto

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{BASE_URL}/works",
                    params=params,
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OpenAlex search failed: %s", e)
            return []

        results = []
        for work in data.get("results", []):
            try:
                results.append(self._to_result(work))
            except Exception as e:
                logger.debug("Skip OpenAlex result: %s", e)
        return results

    def _to_result(self, work: dict) -> PaperResult:
        authors = [
            au.get("author", {}).get("display_name", "")
            for au in work.get("authorships") or []
        ]
        ids = work.get("ids") or {}
        arxiv_id = ""
        if ids.get("arxiv"):
            arxiv_id = ids["arxiv"].replace("https://arxiv.org/abs/", "")

        # 提取发表期刊/会议
        venues = []
        primary_loc = work.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        if source.get("display_name"):
            venues.append(source["display_name"])

        return PaperResult(
            source=self.name,
            title=work.get("title", ""),
            authors=authors,
            abstract=work.get("abstract_inverted_index") and self._decode_abstract(
                work["abstract_inverted_index"]
            ) or "",
            url=work.get("doi", "") or ids.get("doi", ""),
            arxiv_id=arxiv_id,
            published_date=work.get("publication_date") or "",
            citation_count=work.get("cited_by_count") or 0,
            code_url=ids.get("code_repository", ""),
            venues=venues,
        )

    @staticmethod
    def _decode_abstract(inverted_index: dict) -> str:
        """OpenAlex 的 abstract_inverted_index → 纯文本"""
        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)
