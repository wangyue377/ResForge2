"""
LLM 辅助论文元数据提取

用于本地 PDF（无 ArXiv 元数据时）从 PDF 首页提取标题、作者、摘要等信息。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

METADATA_EXTRACTION_PROMPT = """你是一个学术论文元数据提取助手。从以下论文首页文本中提取信息，返回 JSON。

论文文本:
{first_page_text}

请返回以下 JSON 格式（字段不确定则填 null）：
{{
  "title": "完整论文标题",
  "authors": ["作者1", "作者2"],
  "abstract": "摘要全文",
  "journal": "发表的会议/期刊名，如 CVPR 2025，不确定填 null",
  "keywords": ["关键词1", "关键词2"],
  "research_area": ["从以下选: semi_supervised_learning, active_learning, remote_sensing, object_detection, transformer, other"]
}}
"""


class MetadataExtractor:
    """LLM 辅助提取论文元数据"""

    def __init__(self, llm_provider: Any):
        """
        Args:
            llm_provider: 具有 chat_completion 接口的 LLM 提供者
                          (通常是 agent.provider.LLMProvider 或兼容接口)
        """
        self.llm = llm_provider

    async def extract(self, first_page_text: str) -> dict:
        """
        从 PDF 首页文本提取论文元数据。

        Args:
            first_page_text: PDF 第一页提取的文本

        Returns:
            包含 title, authors, abstract 等的字典
        """
        prompt = METADATA_EXTRACTION_PROMPT.format(
            first_page_text=first_page_text[:3000]
        )
        try:
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            logger.warning("Metadata extraction failed: %s", e)
            return {"title": "", "authors": [], "abstract": ""}
