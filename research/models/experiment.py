"""
数据库模型定义 — Experiment & ActiveLearningRound

实验跟踪 + 主动学习轮次追踪。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, JSON, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from research.models.paper import Base


class Experiment(Base):
    """实验主表"""

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_paper_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="SET NULL"),
        nullable=True,
        comment="基准方法对应的论文",
    )

    status: Mapped[str] = mapped_column(
        String(20), default="running", comment="running / completed / failed"
    )
    config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, comment="完整实验配置（模型、超参数等）"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Experiment {self.name} ({self.status})>"


class ActiveLearningRound(Base):
    """主动学习轮次记录"""

    __tablename__ = "active_learning_rounds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    unlabeled_pool_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="该轮开始时未标注池大小"
    )
    queried_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="本轮采样数量"
    )
    sampling_strategy: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="uncertainty / diversity / hybrid"
    )
    budget_ratio: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="本轮采样比例"
    )
    model_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="模型 checkpoint 路径"
    )
    metrics: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, comment='{mAP: 0.75, F1: 0.71, ...}'
    )
    queried_samples: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, comment="本轮查询的样本元数据"
    )
    queried_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ALRound {self.round_number}: {self.sampling_strategy} "
            f"(queried={self.queried_count})>"
        )
