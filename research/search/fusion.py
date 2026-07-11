"""
多源搜索融合引擎

并行从 ArXiv、Semantic Scholar、OpenAlex、DBLP 搜索，
结果去重（基于标题归一化） + 融合排序（按源权重 + 引用数加权）。

查询预处理：
- 自动提取年份范围（如 "2025 2026" → 2025–2026）
- 从语义查询中剥离年份数字
- 按源特性投递不同的查询参数
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from research.search import PaperResult, PaperSource
from research.search.semantic_scholar import SemanticScholarSource
from research.search.openalex import OpenAlexSource
from research.search.dblp import DBLPSource
from research.search.web import WebSearchSource

logger = logging.getLogger(__name__)


# ── 查询预处理 ─────────────────────────────────────────────────────

def preprocess_query(raw: str) -> tuple[str, int | None, int | None]:
    """从原始查询中提取年份范围，返回 (干净查询, 起始年, 结束年)。

    >>> preprocess_query("semi-supervised object detection 2025 2026")
    ("semi-supervised object detection", 2025, 2026)
    >>> preprocess_query("transformer 2023")
    ("transformer", 2023, 2023)
    >>> preprocess_query("no years here")
    ("no years here", None, None)
    """
    years = sorted(set(int(m) for m in re.findall(r"\b(20[2-9]\d)\b", raw) if 2020 <= int(m) <= 2030))
    clean = re.sub(r"\b20[2-9]\d\b", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    if not years:
        return clean, None, None
    return clean, years[0], years[-1]


def _normalize_title(title: str) -> str:
    """标题归一化用于去重：小写、去标点、去空格"""
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9一-鿿]", "", t)
    return t


def _deduplicate(results: list[PaperResult]) -> list[PaperResult]:
    """按归一化标题去重，保留第一出现的"""
    seen: set[str] = set()
    deduped: list[PaperResult] = []
    for r in results:
        key = _normalize_title(r.title)
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


# 各源基础权重（反映召回质量和覆盖面）
SOURCE_WEIGHTS = {
    "arxiv": 1.0,
    "semantic_scholar": 0.95,
    "openalex": 0.85,
    "web": 0.80,
    "dblp": 0.75,
}


def _fusion_sort(
    results: list[PaperResult],
    source_weights: dict[str, float] | None = None,
) -> list[PaperResult]:
    """多因子融合排序：源权重 + 引用数归一化 + 新鲜度"""
    weights = source_weights or SOURCE_WEIGHTS

    if not results:
        return results

    max_citations = max(r.citation_count for r in results)
    max_citations = max(max_citations, 1)

    scored = []
    for r in results:
        base_weight = weights.get(r.source, 0.5)
        citation_score = (r.citation_count / max_citations) * 0.15 if max_citations > 0 else 0
        total = base_weight + citation_score
        scored.append((total, r))

    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored]


class PaperSearcher:
    """多源论文搜索器 —— 四源并行 + 去重 + 融合排序"""

    def __init__(
        self,
        sources: list[PaperSource] | None = None,
        source_weights: dict[str, float] | None = None,
    ):
        self.sources = sources or [
            _ArxivDirectSource(),
            SemanticScholarSource(),
            OpenAlexSource(),
            WebSearchSource(),
            DBLPSource(),
        ]
        self.source_weights = source_weights or SOURCE_WEIGHTS

    async def search(
        self,
        query: str,
        top_k: int = 10,
        source_filter: list[str] | None = None,
    ) -> list[PaperResult]:
        """
        四源并行搜索（自动提取年份范围并传给各源）。

        Args:
            query: 搜索关键词（可含年份，如 "uncertainty sampling 2024 2025"）
            top_k: 每源请求数（实际融合后返回 top_k 条）
            source_filter: 指定源，如 ['arxiv', 'openalex']，默认全开

        Returns:
            融合排序后的 PaperResult 列表
        """
        sources = self.sources
        if source_filter:
            sources = [s for s in sources if s.name in source_filter]

        if not sources:
            return []

        # 预处理查询：提取年份，清理语义部分
        clean_query, year_from, year_to = preprocess_query(query)

        # 并行搜索（传清理后的查询 + 年份范围）
        batch = await _gather_with_errors([
            s.search(clean_query, top_k, year_from=year_from, year_to=year_to)
            for s in sources
        ])

        # 展平 + 去重 + 融合排序
        flat: list[PaperResult] = []
        for results in batch:
            flat.extend(results)

        deduped = _deduplicate(flat)
        sorted_results = _fusion_sort(deduped, self.source_weights)
        return sorted_results[:top_k * 2]  # 多返回一些，给上层再筛选


class _ArxivDirectSource(PaperSource):
    """ArXiv 直连搜索源（通过 export.arxiv.org API，不依赖 arxiv Python 库）"""

    name = "arxiv"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(
        self,
        query: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperResult]:
        import httpx
        import xml.etree.ElementTree as ET

        url = "https://export.arxiv.org/api/query"

        # ArXiv 查询语法：可追加日期范围 all:query AND submittedDate:[YYYYMMDD TO YYYYMMDD]
        date_filter = ""
        if year_from and year_to:
            date_filter = (
                f" AND submittedDate:[{year_from}0101 TO {year_to}1231]"
            )
        elif year_from:
            date_filter = f" AND submittedDate:[{year_from}0101 TO {year_from}1231]"

        queries = [
            f'all:"{query}"{date_filter}',
        ]
        # 如有语义关键词，追加 OR 宽松匹配（取前 6 个非噪声词）
        tokens = [w for w in query.strip().split() if len(w) > 2][:6]
        if tokens:
            queries.append(f'all:{" OR ".join(tokens)}{date_filter}')

        seen_ids = set()
        results = []

        for search_query in queries:
            if len(results) >= top_k:
                break
            params = {
                "search_query": search_query,
                "max_results": min(top_k - len(results) + 5, 50),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    root = ET.fromstring(resp.content)
            except Exception as e:
                logger.warning("ArXiv search failed (query=%s): %s", search_query[:80], e)
                continue

            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                if len(results) >= top_k:
                    break
                try:
                    arxiv_id = ""
                    id_el = entry.find("a:id", ns)
                    if id_el is not None and id_el.text:
                        arxiv_id = id_el.text.strip().split("/")[-1].split("v")[0]

                    if arxiv_id in seen_ids:
                        continue
                    seen_ids.add(arxiv_id)

                    title_el = entry.find("a:title", ns)
                    title = title_el.text.strip().replace("\n", " ").replace("  ", " ") if title_el is not None and title_el.text else ""

                    authors = []
                    for au in entry.findall("a:author/a:name", ns):
                        if au.text:
                            authors.append(au.text.strip())

                    abstract_el = entry.find("a:summary", ns)
                    abstract = abstract_el.text.strip().replace("\n", " ") if abstract_el is not None and abstract_el.text else ""

                    published_el = entry.find("a:published", ns)
                    published = published_el.text[:10] if published_el is not None and published_el.text else ""

                    results.append(PaperResult(
                        source=self.name,
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                        arxiv_id=arxiv_id,
                        published_date=published,
                    ))
                except Exception as e:
                    logger.debug("Skip ArXiv result: %s", e)

        return results[:top_k]


async def _gather_with_errors(coros: list) -> list:
    """asyncio.gather 的容错版本——单源失败不影响其他"""
    import asyncio
    results = await asyncio.gather(*coros, return_exceptions=True)
    return [
        r for r in results
        if not isinstance(r, Exception)
    ]
