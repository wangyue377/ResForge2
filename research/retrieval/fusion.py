"""
RRF 融合排序 (Reciprocal Rank Fusion)

将向量检索和关键词检索结果融合排序。
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


class RRFFusion:
    """倒数排名融合"""

    def __init__(
        self,
        k: int = 60,
        vector_weight: float = 1.0,
        keyword_weight: float = 0.5,
    ):
        """
        Args:
            k: RRF 平滑常数（越大则排名靠后的文档越难提升）
            vector_weight: 向量检索通道权重
            keyword_weight: 关键词检索通道权重
        """
        self.k = k
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight

    def fuse(
        self,
        vector_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        融合两组检索结果，按 RRF 分数降序排列。

        Args:
            vector_results: 向量检索结果 [{id, score, ...}]
            keyword_results: 关键词检索结果 [{id, score, ...}]

        Returns:
            融合后的结果 [{id, ..., fusion_score}, ...]
        """
        rrf_scores: dict[str, float] = {}
        seen: dict[str, dict[str, Any]] = {}

        # 向量通道
        for rank, item in enumerate(vector_results):
            doc_id = str(item["id"])
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (
                self.vector_weight / (self.k + rank + 1)
            )
            seen[doc_id] = item

        # 关键词通道
        for rank, item in enumerate(keyword_results):
            doc_id = str(item["id"])
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (
                self.keyword_weight / (self.k + rank + 1)
            )
            if doc_id not in seen:
                seen[doc_id] = item

        # 按 RRF 分数排序
        ranked = sorted(
            seen.values(),
            key=lambda x: rrf_scores.get(str(x["id"]), 0.0),
            reverse=True,
        )

        for item in ranked:
            item["fusion_score"] = round(
                rrf_scores.get(str(item["id"]), 0.0), 4
            )

        logger.debug(
            "RRF fusion: %d vector + %d keyword → %d fused",
            len(vector_results), len(keyword_results), len(ranked),
        )
        return ranked
