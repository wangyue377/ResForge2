"""
数据库模型定义 — Dataset

常用遥感目标检测数据集元数据。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, ARRAY, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from research.models.paper import Base


class Dataset(Base):
    """遥感目标检测数据集元数据"""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="如 DOTA-v1.0"
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True, comment="全称"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="object_detection / rotated_detection"
    )
    category_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    instance_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    classes: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String(100)), nullable=True
    )
    annotation_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="HBB / OBB / HBB+OBB"
    )
    published_in: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="相关论文/期刊"
    )
    download_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Dataset {self.name}>"
