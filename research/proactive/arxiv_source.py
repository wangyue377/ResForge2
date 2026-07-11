"""
ArXiv 文献推送源

对接 Akashic Proactive 系统的 alert/content/context 三路协议，
实现 ArXiv 新论文的自动监控和推送。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 研究方向关键词权重
_KEYWORD_WEIGHTS = {
    # 半监督学习 (权重 0.4)
    "semi-supervised": 0.4,
    "consistency": 0.35,
    "pseudo-label": 0.4,
    "self-training": 0.35,
    "mean teacher": 0.4,
    "fixmatch": 0.4,
    "soft teacher": 0.4,
    "unbiased teacher": 0.35,
    "teacher-student": 0.3,
    "dense teacher": 0.35,
    # 主动学习 (权重 0.4)
    "active learning": 0.4,
    "uncertainty": 0.35,
    "query strategy": 0.35,
    "budget": 0.25,
    "core-set": 0.35,
    "bald": 0.35,
    "mc-dropout": 0.3,
    "learning loss": 0.3,
    "sample selection": 0.3,
    # 遥感 (权重 0.3)
    "remote sensing": 0.3,
    "optical remote": 0.25,
    "satellite": 0.2,
    "aerial": 0.2,
    "dota": 0.3,
    "hrsc2016": 0.25,
    "dior": 0.25,
    "fair1m": 0.25,
    # 目标检测 (权重 0.15)
    "object detection": 0.15,
    "rotated object": 0.15,
    "oriented object": 0.15,
    "small object": 0.1,
    "faster r-cnn": 0.1,
    "yolo": 0.1,
    "retinanet": 0.1,
    "detr": 0.1,
    "transformer": 0.05,
}


class ArxivProactiveSource:
    """ArXiv 文献监控源"""

    def __init__(
        self,
        config,
        embedder=None,
        db=None,
        categories: Optional[list[str]] = None,
    ):
        self.config = config
        self.embedder = embedder
        self.db = db
        self.categories = categories or ["cs.CV", "cs.AI", "cs.LG"]
        self._seen_ids: set[str] = set()

    async def fetch_alert(self) -> list[dict]:
        """
        高优先级 alert：高度相关论文（半监督/主动学习 + 遥感检测）

        返回格式：[{title, body, score, source, url}, ...]
        """
        from research.ingestion.arxiv_loader import ArxivLoader

        loader = ArxivLoader()
        query = (
            '("semi-supervised" OR "active learning") AND '
            '("remote sensing" OR "object detection" OR "DOTA")'
        )
        try:
            papers = await loader.search(query=query, max_results=5, sort_by="submitted")
        except Exception as e:
            logger.warning("ArXiv alert fetch failed: %s", e)
            return []

        alerts = []
        for p in papers:
            score = self._relevance_score(p)
            if score >= 0.7 and p["arxiv_id"] not in self._seen_ids:
                self._seen_ids.add(p["arxiv_id"])
                alerts.append({
                    "title": f"📄 【高相关】{p['title'][:80]}",
                    "body": (
                        f"作者: {', '.join(p['authors'][:3])}...\n"
                        f"相关度: {score:.0%}\n"
                        f"摘要: {p.get('abstract', '')[:300]}...\n"
                        f"🔗 {p['paper_url']}"
                    ),
                    "score": score,
                    "source": "arxiv_alert",
                    "url": p["paper_url"],
                })
        return alerts

    async def fetch_content(self) -> list[dict]:
        """
        中优先级 content：领域相关论文流
        """
        from research.ingestion.arxiv_loader import ArxivLoader

        loader = ArxivLoader()

        # 在配置的类别中搜索
        cat_query = " OR ".join(f"cat:{c}" for c in self.categories)
        try:
            papers = await loader.search(
                query=f"({cat_query}) AND (semi-supervised OR active_learning)",
                max_results=self.config.max_results,
                sort_by="submitted",
            )
        except Exception as e:
            logger.warning("ArXiv content fetch failed: %s", e)
            return []

        contents = []
        for p in papers:
            score = self._relevance_score(p)
            if score >= self.config.relevance_threshold and p["arxiv_id"] not in self._seen_ids:
                self._seen_ids.add(p["arxiv_id"])
                contents.append({
                    "title": p["title"],
                    "body": (
                        f"相关度: {score:.0%}  |  "
                        f"{', '.join(p['authors'][:2])}...\n"
                        f"摘要: {p.get('abstract', '')[:300]}...\n"
                        f"🔗 {p['paper_url']}"
                    ),
                    "score": score,
                    "source": "arxiv_content",
                    "url": p["paper_url"],
                })
        return contents

    async def fetch_context(self) -> list[dict]:
        """低优先级 context：暂不实现"""
        return []

    def _relevance_score(self, paper: dict) -> float:
        """
        计算论文与研究方向的相关性分数。

        策略：标题和摘要中匹配的关键词加权求和，上限 1.0。
        """
        text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
        score = 0.0
        for keyword, weight in _KEYWORD_WEIGHTS.items():
            if keyword in text:
                score += weight
        return min(score, 1.0)
