"""
论文代码搜索 — 通过 GitHub API 和 PapersWithCode 查找论文的官方实现
"""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# GitHub 搜索 API（无需认证，但有速率限制 60 req/hr）
GITHUB_API = "https://api.github.com"


async def find_code_for_paper(arxiv_id: str) -> str:
    """
    通过 PapersWithCode + GitHub 搜索论文的官方代码。

    Returns:
        代码仓库 URL 或空字符串
    """
    # 方法1: PapersWithCode
    url = f"https://paperswithcode.com/api/v1/papers/?arxiv_id={arxiv_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results and results[0].get("paper_url"):
                    return results[0]["paper_url"]
    except Exception as e:
        logger.debug("PapersWithCode lookup failed: %s", e)

    # 方法2: GitHub 直接搜 readme 中提到的 arxiv id
    repo_url = await _search_github(f"arxiv {arxiv_id} in:readme", sort="stars")
    if repo_url:
        return repo_url

    # 方法3: 搜 repo name
    short_id = arxiv_id.replace(".", "_").replace("-", "_")
    repo_url = await _search_github(f"{short_id} in:name", sort="stars")
    if repo_url:
        return repo_url

    return ""


async def search_github_by_title(title: str, top_k: int = 5) -> list[dict]:
    """
    按论文标题搜索 GitHub 仓库。

    Returns:
        [{url, repo, description, stars}, ...]
    """
    # 提取关键短语（去掉常见论文词缀）
    query = re.sub(r"\s*:?\s*(A|An|The)\s+", " ", title)
    query = re.sub(r"\s+", " ", query).strip()
    words = [w for w in query.split() if len(w) > 3][:8]
    query = " ".join(words) if words else title

    results = await _search_github_repos(f"{query} in:name,readme", top_k=top_k)
    return results


async def _search_github(query: str, sort: str = "stars") -> str:
    """GitHub 搜索，返回第一个仓库 URL（如有）"""
    results = await _search_github_repos(query, top_k=1, sort=sort)
    return results[0]["url"] if results else ""


async def _search_github_repos(query: str, top_k: int = 5, sort: str = "stars") -> list[dict]:
    """GitHub 仓库搜索"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GITHUB_API}/search/repositories",
                params={"q": query, "sort": sort, "per_page": top_k},
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("items", [])[:top_k]:
                    results.append({
                        "url": item["html_url"],
                        "repo": item["full_name"],
                        "description": item.get("description") or "",
                        "stars": item.get("stargazers_count", 0),
                    })
                return results
    except Exception as e:
        logger.debug("GitHub search failed: %s", e)
    return []
