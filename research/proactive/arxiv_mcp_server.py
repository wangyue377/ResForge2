"""
ArXiv MCP Server — 供 Proactive 系统轮询论文推送

启动方式：
  uv run python research/proactive/arxiv_mcp_server.py

MCP 协议 (JSON-RPC over stdio)：
  - tools/list → 返回工具列表
  - tools/call → 执行 arxiv_fetch_alert / arxiv_fetch_content / arxiv_ack
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("arxiv-mcp")

# ── 两路研究方向的搜索配置 ─────────────────────────────

# ① 半监督学习 + 遥感目标检测
SSL_QUERY = '("semi-supervised" OR "consistency regularization" OR "pseudo-label" OR "self-training" OR "mean teacher" OR "fixmatch" OR "soft teacher" OR "unbiased teacher" OR "dense teacher" OR "cross-teacher") AND ("remote sensing" OR "object detection" OR "DOTA" OR "optical" OR "satellite" OR "aerial")'

# ② 主动学习 + 遥感目标检测
AL_QUERY = '("active learning" OR "uncertainty sampling" OR "query strategy" OR "core-set" OR "bald" OR "mc-dropout" OR "learning loss" OR "sample selection" OR "budget allocation") AND ("remote sensing" OR "object detection" OR "DOTA" OR "optical" OR "satellite" OR "aerial")'

# 研究方向关键词权重
_SSL_WEIGHTS: dict[str, float] = {
    "semi-supervised": 0.5, "consistency": 0.45, "pseudo-label": 0.5,
    "self-training": 0.45, "mean teacher": 0.5, "fixmatch": 0.5,
    "soft teacher": 0.5, "unbiased teacher": 0.45, "teacher-student": 0.4,
    "dense teacher": 0.45, "cross-teacher": 0.4, "pseudo-labeling": 0.45,
    "weakly-supervised": 0.3, "semi": 0.3,
}

_AL_WEIGHTS: dict[str, float] = {
    "active learning": 0.5, "uncertainty": 0.45, "query strategy": 0.45,
    "core-set": 0.45, "bald": 0.45, "mc-dropout": 0.4,
    "learning loss": 0.4, "sample selection": 0.4, "budget": 0.35,
    "query-by-committee": 0.4, "expected model change": 0.4,
    "diversity sampling": 0.35, "hybrid sampling": 0.35,
}

_RSOD_WEIGHTS: dict[str, float] = {
    "remote sensing": 0.35, "optical remote": 0.3, "satellite": 0.25,
    "aerial": 0.25, "dota": 0.35, "hrsc2016": 0.3, "dior": 0.3,
    "fair1m": 0.3, "object detection": 0.2, "rotated object": 0.2,
    "oriented object": 0.2, "small object": 0.15, "ship detection": 0.2,
    "airplane detection": 0.15, "vehicle detection": 0.15,
    "faster r-cnn": 0.12, "yolo": 0.12, "detr": 0.12,
    "retinanet": 0.12, "transformer": 0.08,
}


def relevance_score(paper: dict) -> float:
    """三方向加权评分：SSL + AL + RSOD，各自加总后上限 1.0"""
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    ssl = sum(w for k, w in _SSL_WEIGHTS.items() if k in text)
    al = sum(w for k, w in _AL_WEIGHTS.items() if k in text)
    rsod = sum(w for k, w in _RSOD_WEIGHTS.items() if k in text)
    # 至少有一个主方向 + 遥感方向同时命中才算高相关
    has_main = ssl >= 0.3 or al >= 0.3
    has_rsod = rsod >= 0.15
    raw = min(ssl + al + rsod, 1.0)
    # 如果主方向和遥感方向都没有明显信号，降权
    if not has_main:
        raw *= 0.3
    elif not has_rsod:
        raw *= 0.5
    return round(min(raw, 1.0), 2)

def build_result(papers: list[dict], source_name: str, min_score: float) -> list[dict]:
    """构建 MCP result 格式"""
    results = []
    for p in papers:
        score = relevance_score(p)
        label = {"arxiv_alert_ssl": "SSL", "arxiv_alert_al": "AL",
                 "arxiv_content_ssl": "SSL流", "arxiv_content_al": "AL流"}.get(source_name, "")
        if score >= min_score:
            results.append({
                "id": f"arxiv:{p['arxiv_id']}",
                "title": f"[{label}] {p['title']}",
                "body": (
                    f"相关度: {score:.0%}  |  {', '.join(p['authors'][:2])}...\n"
                    f"{p['abstract'][:300]}...\n"
                    f"🔗 https://arxiv.org/abs/{p['arxiv_id']}"
                ),
                "score": score,
                "url": f"https://arxiv.org/abs/{p['arxiv_id']}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "source_name": source_name,
                "_ack_server": "arxiv-mcp",
                "_ack_tool": "arxiv_ack",
            })
    return results


async def fetch_arxiv(query: str, max_results: int = 10) -> list[dict]:
    """调用 ArXiv API 搜索论文"""
    import httpx
    import xml.etree.ElementTree as ET

    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": query,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    papers = []
    for entry in root.findall("a:entry", ns):
        id_elem = entry.find("a:id", ns)
        arxiv_id = id_elem.text.split("/")[-1].split("v")[0] if id_elem is not None and id_elem.text else ""
        title = (entry.find("a:title", ns).text or "").replace("\n", " ").strip()
        summary = (entry.find("a:summary", ns).text or "").replace("\n", " ").strip()
        authors = [a.find("a:name", ns).text for a in entry.findall("a:author", ns) if a.find("a:name", ns) is not None]
        published = entry.find("a:published", ns).text if entry.find("a:published", ns) is not None else ""
        link = ""
        for l in entry.findall("a:link", ns):
            if l.attrib.get("title") == "pdf":
                link = l.attrib.get("href", "")
                break
        papers.append({
            "arxiv_id": arxiv_id,
            "title": title[:300],
            "authors": authors[:5],
            "abstract": summary[:500],
            "published": published[:10],
            "pdf_url": link,
        })
    return papers


# ── MCP Server ──────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "arxiv_alert_ssl",
        "description": "半监督学习 + 遥感目标检测 — 高相关论文推送 (score≥0.6)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "arxiv_alert_al",
        "description": "主动学习 + 遥感目标检测 — 高相关论文推送 (score≥0.6)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "arxiv_content_ssl",
        "description": "半监督学习领域新论文流 (score≥0.45)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "最大返回数", "default": 15}
            },
        },
    },
    {
        "name": "arxiv_content_al",
        "description": "主动学习领域新论文流 (score≥0.45)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "最大返回数", "default": 15}
            },
        },
    },
    {
        "name": "arxiv_ack",
        "description": "确认已处理某篇论文，标记已读避免重复推送",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}, "description": "已处理的 arxiv_id 列表"}
            },
            "required": ["ids"],
        },
    },
]


class ArxivMCPServer:
    """ArXiv MCP 服务器 — stdio 传输层"""

    def __init__(self):
        self._seen: set[str] = set()

    async def handle_request(self, request: dict) -> dict:
        method = request.get("method", "")
        req_id = request.get("id", 0)
        params = request.get("params", {}) or {}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

        elif method == "tools/call":
            tool = params.get("name", "")
            args = params.get("arguments", {}) or {}

            if tool == "arxiv_alert_ssl":
                papers = await fetch_arxiv(SSL_QUERY, max_results=5)
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(build_result(papers, "arxiv_alert_ssl", 0.55), ensure_ascii=False)}]}}

            elif tool == "arxiv_alert_al":
                papers = await fetch_arxiv(AL_QUERY, max_results=5)
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(build_result(papers, "arxiv_alert_al", 0.55), ensure_ascii=False)}]}}

            elif tool == "arxiv_content_ssl":
                max_results = int(args.get("max_results", 15))
                papers = await fetch_arxiv(SSL_QUERY, max_results=max_results)
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(build_result(papers, "arxiv_content_ssl", 0.4), ensure_ascii=False)}]}}

            elif tool == "arxiv_content_al":
                max_results = int(args.get("max_results", 15))
                papers = await fetch_arxiv(AL_QUERY, max_results=max_results)
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(build_result(papers, "arxiv_content_al", 0.4), ensure_ascii=False)}]}}

            elif tool == "arxiv_ack":
                ids = args.get("ids", [])
                self._seen.update(ids)
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"text": f"acked {len(ids)} ids"}]}}

            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown tool: {tool}"}}

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}

    async def run(self):
        """stdio 事件循环"""
        stdin = sys.stdin.buffer
        buffer = b""
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, stdin.readline)
            if not line:
                break
            buffer += line
            try:
                request = json.loads(buffer.decode())
                buffer = b""
                response = await self.handle_request(request)
                resp_line = json.dumps(response, ensure_ascii=False) + "\n"
                sys.stdout.buffer.write(resp_line.encode())
                sys.stdout.buffer.flush()
            except json.JSONDecodeError:
                continue  # 可能只读了半行


if __name__ == "__main__":
    asyncio.run(ArxivMCPServer().run())
