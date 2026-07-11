"""
数据库模型定义 — Paper & PaperChunk

论文主表 + 文本分块表，支持 pgvector 向量检索。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Text, Date, Float, Integer, ARRAY, JSON, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Paper(Base):
    """论文主表"""

    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    arxiv_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String(200)), nullable=True
    )
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    paper_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    code_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bibtex: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String(100)), nullable=True
    )
    research_area: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String(100)), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="imported", comment="imported / parsed / indexed"
    )
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks = relationship(
        "PaperChunk",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperChunk.chunk_index",
    )

    def __repr__(self) -> str:
        return f"<Paper {self.arxiv_id or self.id}: {self.title[:60]}...>"


class PaperChunk(Base):
    """论文文本分块（含语义向量）"""

    __tablename__ = "paper_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="所属章节名"
    )
    content_type: Mapped[str] = mapped_column(
        String(20), default="text", comment="text / table / figure_caption"
    )
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 注意：embedding 字段在原始 SQL 中通过 pgvector 扩展管理，
    # SQLAlchemy 侧用 TEXT 占位，实际 DDL 需手动执行：
    # ALTER TABLE paper_chunks ADD COLUMN embedding vector(1024);
    # CREATE INDEX ON paper_chunks USING hnsw (embedding vector_cosine_ops);

    paper = relationship("Paper", back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<PaperChunk {self.paper_id}:{self.chunk_index} "
            f"({self.section or 'nosection'})>"
        )
