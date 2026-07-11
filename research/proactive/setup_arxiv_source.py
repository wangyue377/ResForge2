"""
配置 ArXiv + 飞书 MCP 数据源到 Proactive 系统

生成 ~/.akashic/workspace/ 下的两个配置文件：
  - mcp_servers.json      —— MCP server 连接配置
  - proactive_sources.json —— 数据源配置（alert + content 双通道）

Proactive Loop 启动时会自动读取这些文件并连接。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = Path.home() / ".akashic" / "workspace"


def ensure_arxiv_mcp_config(workspace: Path | None = None) -> bool:
    """
    确保 ArXiv MCP 源配置存在于 workspace 中。
    如果已有则跳过，没有则生成。

    Returns:
        True 表示配置就绪（已有或新建成功）
    """
    ws = workspace or DEFAULT_WORKSPACE
    ws.mkdir(parents=True, exist_ok=True)

    mcp_servers_path = ws / "mcp_servers.json"
    sources_path = ws / "proactive_sources.json"

    mcp_updated = _ensure_mcp_servers(mcp_servers_path)
    sources_updated = _ensure_sources(sources_path)

    if mcp_updated or sources_updated:
        logger.info("MCP config initialized in %s", ws)
    else:
        logger.debug("MCP config already up to date")

    return True


def _ensure_mcp_servers(path: Path) -> bool:
    """注入 arxiv-mcp + feishu-mcp server 配置"""
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, Exception):
            existing = {}

    servers = existing.get("servers", {})
    updated = False

    # ArXiv MCP
    if "arxiv-mcp" not in servers:
        servers["arxiv-mcp"] = {
            "command": [
                "uv", "run", "--directory", str(Path.cwd()),
                "python", "research/proactive/arxiv_mcp_server.py",
            ],
            "env": {},
            "description": "ArXiv 论文监控 — 按研究方向关键词推送新论文",
        }
        updated = True

    # 飞书 MCP
    if "feishu-mcp" not in servers:
        servers["feishu-mcp"] = {
            "command": [
                "uv", "run", "--directory", str(Path.cwd()),
                "python", "research/proactive/feishu_mcp_server.py",
            ],
            "env": {
                "FEISHU_APP_ID": "",
                "FEISHU_APP_SECRET": "",
            },
            "description": "飞书文档监控 — 推送近期更新的文档",
        }
        updated = True

    # Semantic Scholar MCP
    if "semantic-scholar-mcp" not in servers:
        servers["semantic-scholar-mcp"] = {
            "command": [
                "uv", "run", "--directory", str(Path.cwd()),
                "python", "research/proactive/semantic_scholar_mcp_server.py",
            ],
            "env": {},
            "description": "Semantic Scholar 论文监控 — 含引用数信息",
        }
        updated = True

    # OpenAlex MCP
    if "openalex-mcp" not in servers:
        servers["openalex-mcp"] = {
            "command": [
                "uv", "run", "--directory", str(Path.cwd()),
                "python", "research/proactive/openalex_mcp_server.py",
            ],
            "env": {},
            "description": "OpenAlex 论文监控 — 含代码链接信息",
        }
        updated = True

    # DBLP MCP
    if "dblp-mcp" not in servers:
        servers["dblp-mcp"] = {
            "command": [
                "uv", "run", "--directory", str(Path.cwd()),
                "python", "research/proactive/dblp_mcp_server.py",
            ],
            "env": {},
            "description": "DBLP 论文监控 — 计算机科学文献",
        }
        updated = True

    if updated:
        path.write_text(json.dumps({"servers": servers}, indent=2, ensure_ascii=False))
        logger.info("Added MCP servers to %s", path)

    return updated


def _ensure_sources(path: Path) -> bool:
    """注入 ArXiv + 飞书 数据源"""
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, Exception):
            existing = {}

    sources = existing.get("sources", [])
    existing_names = {s.get("name", "") for s in sources}
    added = False

    # ArXiv 源
    arxiv_sources = [
        ("arxiv-alert-ssl", "arxiv-mcp", "alert", "arxiv_alert_ssl"),
        ("arxiv-alert-al", "arxiv-mcp", "alert", "arxiv_alert_al"),
        ("arxiv-content-ssl", "arxiv-mcp", "content", "arxiv_content_ssl"),
        ("arxiv-content-al", "arxiv-mcp", "content", "arxiv_content_al"),
    ]
    for name, server, channel, tool in arxiv_sources:
        if name not in existing_names:
            sources.append({
                "name": name, "server": server,
                "channel": channel, "poll_tool": tool, "enabled": True,
            })
            added = True

    # 飞书源（content 通道）
    if "feishu-content" not in existing_names:
        sources.append({
            "name": "feishu-content",
            "server": "feishu-mcp",
            "channel": "content",
            "poll_tool": "feishu_fetch_content",
            "enabled": True,
        })
        added = True

    # Semantic Scholar 源（content 通道）
    if "ss-content" not in existing_names:
        sources.append({
            "name": "ss-content",
            "server": "semantic-scholar-mcp",
            "channel": "content",
            "poll_tool": "ss_fetch_content",
            "enabled": True,
        })
        added = True

    # OpenAlex 源（content 通道）
    if "oa-content" not in existing_names:
        sources.append({
            "name": "oa-content",
            "server": "openalex-mcp",
            "channel": "content",
            "poll_tool": "oa_fetch_content",
            "enabled": True,
        })
        added = True

    # DBLP 源（content 通道）
    if "dblp-content" not in existing_names:
        sources.append({
            "name": "dblp-content",
            "server": "dblp-mcp",
            "channel": "content",
            "poll_tool": "dblp_fetch_content",
            "enabled": True,
        })
        added = True

    if added:
        path.write_text(json.dumps({"sources": sources}, indent=2, ensure_ascii=False))
        logger.info("Added sources to %s", path)

    return added
