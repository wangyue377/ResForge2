"""
学术论文语义分块器

按章节标题分割，长章节内按滑动窗口切分。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 学术论文常见章节标题
SECTION_HEADINGS = re.compile(
    r"^(?:"
    r"#{1,3}\s+|"                      # Markdown 标题
    r"(?:\d+\.?\s*)?(?:"
    r"Abstract|Introduction|Related Work|Background"
    r"|Method|Approach|Proposed Method|Framework"
    r"|Experiment|Experimental Setup|Results|Discussion"
    r"|Conclusion|Conclusion and Future Work"
    r"|Appendix|References|Supplementary|Acknowledgment"
    r"|Preliminary|Problem Definition|Overview"
    r"|Ablation Study|Qualitative Analysis|Quantitative Analysis"
    r"|Implementation Details|Training Details"
    r")"
    r")",
    re.IGNORECASE,
)


class PaperChunker:
    """面向学术论文的语义分块器"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        """
        Args:
            chunk_size: 每块的最大单词数
            chunk_overlap: 相邻块之间的重叠单词数
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_paper(self, text: str) -> list[dict]:
        """
        将论文全文分成语义块。

        策略：
        1. 先按章节标题分割（保持语义完整性）
        2. 长章节内按滑动窗口切分
        3. 每块记录所属章节名

        Returns:
            [{"chunk_index": int, "section": str, "content": str}, ...]
        """
        sections = self._split_by_headings(text)
        chunks = []

        for section_title, section_content in sections:
            if not section_content.strip():
                continue
            sub_chunks = self._split_long_section(section_content)
            for sc in sub_chunks:
                if not sc.strip():
                    continue
                chunks.append({
                    "chunk_index": len(chunks),
                    "section": section_title or "NoHeading",
                    "content": sc.strip(),
                })

        logger.info("Split into %d chunks across %d sections", len(chunks), len(sections))
        return chunks

    def _split_by_headings(self, text: str) -> list[tuple[str, str]]:
        """按章节标题将全文分割成 (标题, 内容) 列表"""
        lines = text.split("\n")
        sections = []
        current_heading = ""
        current_lines: list[str] = []

        for line in lines:
            if SECTION_HEADINGS.match(line.strip()):
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines)))
                current_heading = line.strip()[:80]
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_heading, "\n".join(current_lines)))

        return sections

    def _split_long_section(self, content: str) -> list[str]:
        """长章节按滑动窗口切分"""
        words = content.split()
        if len(words) <= self.chunk_size:
            return [content]

        chunks = []
        start = 0
        while start < len(words):
            end = start + self.chunk_size
            chunk = " ".join(words[start:end])
            if chunk.strip():
                chunks.append(chunk)
            start += self.chunk_size - self.chunk_overlap

        return chunks
