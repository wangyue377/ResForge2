"""
Agent 工具定义 — 实验跟踪与主动学习轮次管理
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from agent.tools.base import Tool

logger = logging.getLogger(__name__)


class CreateExperimentTool(Tool):
    """创建一个新的实验记录"""

    name = "create_experiment"
    description = "创建一个新的科研实验记录，用于跟踪训练配置、数据集和结果。创建后可记录多轮主动学习迭代。"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "实验名称，如 'ActiveTeacher_DOTA_5%'",
            },
            "config": {
                "type": "object",
                "description": "实验配置 JSON，包含模型、骨干网络、半监督方法、主动学习策略、数据集、超参数等",
            },
            "description": {
                "type": "string",
                "description": "实验描述",
            },
        },
        "required": ["name", "config"],
    }

    def __init__(self, db: Any, **kwargs):
        super().__init__(**kwargs)
        self.db = db

    async def execute(self, **kwargs) -> str:
        name = kwargs["name"]
        config = kwargs["config"]
        description = kwargs.get("description", "")

        experiment_id = str(uuid.uuid4())
        async with self.db.get_session() as session:
            await session.execute(
                text("""
                    INSERT INTO experiments (id, name, description, config, status, started_at)
                    VALUES (:id, :name, :description, :config, 'running', :started_at)
                """),
                {
                    "id": experiment_id,
                    "name": name,
                    "description": description,
                    "config": json.dumps(config),
                    "started_at": datetime.now(timezone.utc),
                },
            )

        return (
            f"✅ 实验已创建\n\n"
            f"📌 **{name}**\n"
            f"🆔 ID: {experiment_id}\n"
            f"⚙️ 配置: {json.dumps(config, ensure_ascii=False, indent=2)[:500]}\n\n"
            f"可用命令:\n"
            f"- `track_al_round experiment_id={experiment_id} round_number=1 ...` 记录主动学习轮次\n"
            f"- `compare_experiments {experiment_id}` 查看结果"
        )


class TrackALRoundTool(Tool):
    """记录主动学习的一轮迭代结果"""

    name = "track_al_round"
    description = "记录主动学习的一轮迭代：采样策略、查询样本数、训练后的评估指标。每个 round_number 递增。"
    parameters = {
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "实验 ID（从 create_experiment 返回）",
            },
            "round_number": {
                "type": "integer",
                "description": "主动学习轮次编号（从 1 开始递增）",
            },
            "sampling_strategy": {
                "type": "string",
                "description": "采样策略：uncertainty / diversity / hybrid / random",
            },
            "queried_count": {
                "type": "integer",
                "description": "本轮从未标注池中查询的样本数量",
            },
            "metrics": {
                "type": "object",
                "description": "评估指标 JSON，如 {'mAP': 0.754, 'F1': 0.712}",
            },
            "model_path": {
                "type": "string",
                "description": "本轮训练后的模型 checkpoint 路径（可选）",
            },
        },
        "required": ["experiment_id", "round_number", "metrics"],
    }

    def __init__(self, db: Any, **kwargs):
        super().__init__(**kwargs)
        self.db = db

    async def execute(self, **kwargs) -> str:
        round_id = str(uuid.uuid4())
        async with self.db.get_session() as session:
            await session.execute(
                text("""
                    INSERT INTO active_learning_rounds
                        (id, experiment_id, round_number, sampling_strategy,
                         queried_count, metrics, model_path)
                    VALUES (:id, :eid, :round, :strategy, :queried, :metrics, :model)
                """),
                {
                    "id": round_id,
                    "eid": kwargs["experiment_id"],
                    "round": kwargs["round_number"],
                    "strategy": kwargs.get("sampling_strategy", ""),
                    "queried": kwargs.get("queried_count", 0),
                    "metrics": json.dumps(kwargs["metrics"]),
                    "model": kwargs.get("model_path", ""),
                },
            )

        metrics_str = ", ".join(
            f"{k}={v}" for k, v in kwargs["metrics"].items()
        )
        return (
            f"✅ 主动学习 Round {kwargs['round_number']} 已记录\n"
            f"📊 指标: {metrics_str}\n"
            f"🎯 采样策略: {kwargs.get('sampling_strategy', 'N/A')}\n"
            f"📦 采样数量: {kwargs.get('queried_count', 'N/A')}"
        )


class CompareExperimentsTool(Tool):
    """对比多个实验的指标"""

    name = "compare_experiments"
    description = "对比多个实验的最终或各轮次指标，生成横向对比表。"
    parameters = {
        "type": "object",
        "properties": {
            "experiment_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要对比的实验 ID 列表，如 ['id1', 'id2']",
            },
        },
        "required": ["experiment_ids"],
    }

    def __init__(self, db: Any, **kwargs):
        super().__init__(**kwargs)
        self.db = db

    async def execute(self, **kwargs) -> str:
        ids = kwargs["experiment_ids"]
        if not ids:
            return "请提供至少一个实验 ID。"

        async with self.db.get_session() as session:
            # 查询实验信息
            rows = (await session.execute(
                text("""
                    SELECT id, name, status, config, started_at
                    FROM experiments WHERE id = ANY(:ids)
                    ORDER BY created_at
                """),
                {"ids": ids},
            )).fetchall()

            if not rows:
                return "未找到指定的实验。"

            # 查询各实验的主动学习轮次
            lines = ["## 实验对比\n"]
            lines.append("| 实验 | 状态 | 配置摘要 | 主动学习轮次 |")
            lines.append("|------|------|----------|-------------|")

            for row in rows:
                exp_id = row[0]
                rounds = (await session.execute(
                    text("""
                        SELECT round_number, sampling_strategy, metrics, queried_count
                        FROM active_learning_rounds
                        WHERE experiment_id = :eid
                        ORDER BY round_number
                    """),
                    {"eid": exp_id},
                )).fetchall()

                config_summary = ""
                if row[3]:
                    try:
                        cfg = json.loads(row[3]) if isinstance(row[3], str) else row[3]
                        parts = []
                        for k in ["model", "dataset", "ssl_method", "al_strategy"]:
                            if k in cfg:
                                parts.append(f"{k}={cfg[k]}")
                        config_summary = ", ".join(parts) or json.dumps(cfg)[:80]
                    except (json.JSONDecodeError, TypeError):
                        config_summary = str(row[3])[:80]

                round_summary = "; ".join(
                    f"R{r[0]}: {r[2].get('mAP', '?') if isinstance(r[2], dict) else r[2]}"
                    for r in rounds
                ) if rounds else "无轮次记录"

                lines.append(
                    f"| {row[1][:40]} | {row[2]} | {config_summary[:50]} | {round_summary[:80]} |"
                )

            return "\n".join(lines)
