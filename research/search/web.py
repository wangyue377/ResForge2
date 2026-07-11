"""
Web 搜索源 — 基于 Exa MCP 公开端点

作为第五搜索源，补充学术数据库未收录的最新会议论文、期刊文章。
主要覆盖 openaccess.thecvf.com、ieeexplore.ieee.org、springer.com 等。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from research.search import PaperResult, PaperSource

logger = logging.getLogger(__name__)

_EXA_MCP_URL = "https://mcp.exa.ai/mcp"


class WebSearchSource(PaperSource):
    """通用 Web 搜索源（Exa），侧重学术/技术内容"""

    name = "web"

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    async def search(
        self,
        query: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperResult]:
        # 增强查询：加上学术关键词引导 Exa 返回论文类结果
        enhanced = query
        if not any(kw in query.lower() for kw in ["paper", "arxiv", "cvpr", "iccv", "tpami", "neurips"]):
            enhanced = f"{query} paper"
        if year_from and year_to:
            enhanced = f"{enhanced} {year_from} {year_to}"
        elif year_from:
            enhanced = f"{enhanced} {year_from}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "name": "web_search_exa",
            "params": {
                "name": "web_search_exa",
                "arguments": {
                    "query": enhanced,
                    "numResults": min(top_k * 2, 20),
                    "livecrawl": "fallback",
                    "type": "auto",
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    _EXA_MCP_URL,
                    json=payload,
                    headers={
                        "accept": "application/json, text/event-stream",
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return []

        results = []
        raw_items = self._parse_exa_response(data)
        for item in raw_items[:top_k]:
            try:
                results.append(self._to_result(item))
            except Exception as e:
                logger.debug("Skip web result: %s", e)
        return results

    def _parse_exa_response(self, data: Any) -> list[dict]:
        """解析 Exa MCP JSON-RPC 响应"""
        if isinstance(data, dict) and "result" in data:
            content = data["result"].get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "json":
                    parsed = json.loads(block["text"])
                    return parsed.get("results", parsed if isinstance(parsed, list) else [])
        return []

    def _to_result(self, item: dict) -> PaperResult:
        title = item.get("title", "")
        url = item.get("url", "")
        content_text = item.get("content", "") or item.get("text", "") or ""

        # 从 URL 提取 arxiv_id（如有）
        arxiv_id = ""
        if "arxiv.org" in url:
            import re
            m = re.search(r"abs/(\d+\.\d+)", url)
            if m:
                arxiv_id = m.group(1)

        return PaperResult(
            source=self.name,
            title=title,
            authors=[],
            abstract=content_text[:500],
            url=url,
            arxiv_id=arxiv_id,
            published_date=item.get("publishedDate", ""),
            citation_count=0,
            venues=[],
        )
