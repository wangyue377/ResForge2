"""
PDF 学术论文文本提取器

使用 PyMuPDF (fitz) 从科研论文 PDF 中提取全文文本。
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFParser:
    """科研论文 PDF 文本提取"""

    def extract_text(self, pdf_path: str | Path) -> str:
        """
        逐页提取文本。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            全文文本，页之间用换行分隔
        """
        doc = fitz.open(str(pdf_path))
        pages = []
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(f"--- Page {page_num + 1} ---\n{text}")
        doc.close()

        full_text = "\n\n".join(pages)
        logger.info(
            "Extracted %d chars from %s (%d pages)",
            len(full_text), Path(pdf_path).name, len(pages),
        )
        return full_text

    def extract_first_page(self, pdf_path: str | Path) -> str:
        """仅提取第一页（用于 LLM 元数据提取）"""
        doc = fitz.open(str(pdf_path))
        text = doc[0].get_text()
        doc.close()
        return text

    def extract_metadata_raw(self, pdf_path: str | Path) -> dict:
        """提取 PDF 内嵌元数据"""
        doc = fitz.open(str(pdf_path))
        meta = doc.metadata  # dict with title, author, subject, keywords
        doc.close()
        return {
            "pdf_title": meta.get("title", ""),
            "pdf_author": meta.get("author", ""),
            "pdf_subject": meta.get("subject", ""),
            "pdf_keywords": meta.get("keywords", ""),
        }
