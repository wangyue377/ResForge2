"""
DBLP API 论文搜索

API: https://dblp.org/faq/13501473.html
免费额度: 无限制（合理使用），返回 XML 格式
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

import httpx

from research.search import PaperResult, PaperSource

logger = logging.getLogger(__name__)

BASE_URL = "https://dblp.org/search/publ/api"


class DBLPSource(PaperSource):
    """DBLP API 搜索源（计算机科学文献为主）"""

    name = "dblp"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(
        self,
        query: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperResult]:
        _ = year_from  # DBLP API 不支持日期过滤
        _ = year_to
        params: dict[str, Any] = {
            "q": query,
            "h": min(top_k, 100),
            "format": "xml",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    BASE_URL,
                    params=params,
                    headers={"Accept": "application/xml"},
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
        except Exception as e:
            logger.warning("DBLP search failed: %s", e)
            return []

        results = []
        hits = root.findall(".//hit")
        for hit in hits:
            try:
                info = hit.find("info")
                if info is None:
                    continue
                results.append(self._parse_hit(info))
            except Exception as e:
                logger.debug("Skip DBLP result: %s", e)
        return results

    def _parse_hit(self, info: ET.Element) -> PaperResult:
        title_el = info.find("title")
        title = self._get_text(title_el)

        authors = []
        for au in info.findall("authors/author"):
            authors.append(au.text or "")

        abstract_el = info.find("abstract")
        abstract = self._get_text(abstract_el)

        url_el = info.find("url")
        url = self._get_text(url_el)

        year_el = info.find("year")
        year = self._get_text(year_el)
        published_date = f"{year}-01-01" if year else ""

        venue_el = info.find("venue")
        venues = [self._get_text(venue_el)] if venue_el is not None else []

        # DBLP 没有引用数和代码链接
        return PaperResult(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=url,
            published_date=published_date,
            venues=venues,
        )

    @staticmethod
    def _get_text(el: ET.Element | None) -> str:
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _get_attr(el: ET.Element | None, key: str) -> str:
        return el.get(key, "").strip() if el is not None else ""
