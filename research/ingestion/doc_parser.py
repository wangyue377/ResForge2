"""
多格式文档解析器

将 PDF、Word、Excel、PPT、Markdown、代码等格式统一解析为纯文本，
供论文摄入管道后续分块和向量化。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class DocumentParser:
    """多格式文档解析器，按文件扩展名自动路由到对应解析器"""

    def parse(self, file_path: str | Path) -> str:
        """
        解析文件为纯文本。

        Args:
            file_path: 文件路径

        Returns:
            提取的纯文本内容

        Raises:
            ValueError: 不支持的文件格式
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        parser = self._PARSERS.get(ext)
        if parser is None:
            raise ValueError(
                f"不支持的文件格式: {ext}。支持的格式: {', '.join(self._PARSERS.keys())}"
            )
        return parser(str(path))

    def _parse_pdf(self, path: str) -> str:
        """PDF 解析（复用现有 PyMuPDF 逻辑）"""
        import fitz
        doc = fitz.open(path)
        pages = []
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(f"--- Page {page_num + 1} ---\n{text}")
        doc.close()
        text = "\n\n".join(pages)
        logger.info("Parsed PDF: %s (%d chars, %d pages)", Path(path).name, len(text), len(pages))
        return text

    def _parse_docx(self, path: str) -> str:
        """Word 文档解析"""
        from docx import Document
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        # 尝试提取表格
        tables = []
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cells))
            tables.append("\n".join(rows))
        result = "\n\n".join(paragraphs)
        if tables:
            result += "\n\n--- Tables ---\n" + "\n\n".join(tables)
        logger.info("Parsed DOCX: %s (%d chars)", Path(path).name, len(result))
        return result

    def _parse_pptx(self, path: str) -> str:
        """PPT 文档解析"""
        from pptx import Presentation
        prs = Presentation(path)
        slides = []
        for i, slide in enumerate(prs.slides, 1):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        if para.text.strip():
                            texts.append(para.text.strip())
                if shape.has_table:
                    table = shape.table
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        texts.append(" | ".join(cells))
            if texts:
                slides.append(f"--- Slide {i} ---\n" + "\n".join(texts))
        result = "\n\n".join(slides)
        logger.info("Parsed PPTX: %s (%d chars, %d slides)", Path(path).name, len(result), len(slides))
        return result

    def _parse_xlsx(self, path: str) -> str:
        """Excel 文档解析"""
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sheets = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                line = " | ".join(cells)
                if line.strip():
                    rows.append(line)
            if rows:
                sheets.append(f"--- Sheet: {sheet_name} ---\n" + "\n".join(rows))
        wb.close()
        result = "\n\n".join(sheets)
        logger.info("Parsed XLSX: %s (%d chars, %d sheets)", Path(path).name, len(result), len(sheets))
        return result

    def _parse_text(self, path: str) -> str:
        """纯文本/代码文件解析"""
        import locale
        # 尝试常见编码
        for enc in ("utf-8", "gbk", "utf-16", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    text = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            # fallback
            with open(path, "r", encoding="latin-1") as f:
                text = f.read()
        logger.info("Parsed text: %s (%d chars)", Path(path).name, len(text))
        return text

    # 格式路由表
    _PARSERS: dict[str, Callable[[str], str]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self):
        # 构建实例方法路由表
        self._PARSERS = {
            ".pdf":  self._parse_pdf,
            ".docx": self._parse_docx,
            ".doc":  self._parse_docx,
            ".pptx": self._parse_pptx,
            ".ppt":  self._parse_pptx,
            ".xlsx": self._parse_xlsx,
            ".xls":  self._parse_xlsx,
            ".md":   self._parse_text,
            ".txt":  self._parse_text,
            ".py":   self._parse_text,
            ".js":   self._parse_text,
            ".ts":   self._parse_text,
            ".java": self._parse_text,
            ".cpp":  self._parse_text,
            ".c":    self._parse_text,
            ".h":    self._parse_text,
            ".hpp":  self._parse_text,
            ".json": self._parse_text,
            ".xml":  self._parse_text,
            ".yaml": self._parse_text,
            ".yml":  self._parse_text,
            ".toml": self._parse_text,
            ".html": self._parse_text,
            ".css":  self._parse_text,
            ".sql":  self._parse_text,
            ".rst":  self._parse_text,
            ".tex":  self._parse_text,
            ".csv":  self._parse_text,
        }
