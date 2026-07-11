"""
科研论文多源搜索 — 统一结果格式与源基类
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaperResult:
    """统一论文结果格式"""
    source: str                     # 来源标识: arxiv / semantic_scholar / openalex / dblp
    title: str
    authors: list[str]
    abstract: str
    url: str
    arxiv_id: str = ""             # ArXiv ID（如有）
    published_date: str = ""       # ISO 格式日期字符串
    citation_count: int = 0
    code_url: str = ""             # 官方代码仓库链接（如有）
    venues: list[str] = field(default_factory=list)  # 发表会议/期刊


class PaperSource(ABC):
    """搜索源基类，每个数据源实现一个子类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """源标识符"""
        ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 10) -> list[PaperResult]:
        """搜索论文，返回统一格式的结果列表"""
        ...
