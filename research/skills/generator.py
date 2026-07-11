"""
技能自动生成器

分析对话历史中的高频操作模式，自动生成可复用的 SKILL.md。
供 Drift 系统的 auto-skill 调用。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 常见的可沉淀任务模式
SKILL_PATTERNS = {
    "paper-comparison": {
        keywords: ["对比", "比较", "vs", "difference", "有什么不同", "哪个更好", "哪个好"],
        description: "对比多篇论文的方法或指标",
        example: "对比 ActiveTeacher 和 Soft Teacher 在 DOTA 上的结果",
    },
    "dataset-info": {
        keywords: ["数据集信息", "数据集详情", "dataset", "数据集有哪些", "数据集的类别"],
        description: "查询遥感数据集的信息",
        example: "DOTA 数据集有多少个类别？",
    },
    "experiment-log": {
        keywords: ["记录实验", "创建实验", "track experiment", "记一下实验", "实验结果"],
        description: "记录实验配置和主动学习轮次",
        example: "记录实验：ResNet50 + AL on DOTA，第2轮 mAP=0.75",
    },
    "graph-explore": {
        keywords: ["知识图谱", "关系", "相关方法", "引用链", "基于什么改进", "依赖"],
        description: "探索知识图谱中方法与数据集的关系",
        example: "看看 ActiveTeacher 基于哪些工作改进的",
    },
    "arxiv-monitor": {
        keywords: ["最新论文", "新论文", "recent paper", "有没有新论文", "最近有什么"],
        description: "查看 ArXiv 上最新相关论文",
        example: "最近有没有遥感目标检测的新论文？",
    },
    "code-search": {
        keywords: ["代码", "开源", "github", "implement", "复现"],
        description: "查找论文的开源代码或实现",
        example: "ActiveTeacher 的开源代码在哪？",
    },
}

# 各种工具的描述
TOOL_DESCRIPTIONS = {
    "ingest_paper": "从 ArXiv 或 PDF 导入论文",
    "search_papers": "搜索论文知识库",
    "query_graph": "查询知识图谱中的关系",
    "create_experiment": "创建实验记录",
    "track_al_round": "记录主动学习轮次",
    "compare_experiments": "对比多个实验",
}


def analyze_patterns(
    history_text: str,
    recent_context: str,
    memory_items: list[dict] | None = None,
) -> list[dict]:
    """
    分析对话历史，找出可沉淀的技能模式。

    Args:
        history_text: HISTORY.md 的内容
        recent_context: RECENT_CONTEXT.md 的内容
        memory_items: 从记忆系统检索到的相关条目

    Returns:
        [{"pattern", "confidence", "evidence", "description"}, ...]
    """
    text = (history_text + "\n" + (recent_context or "")).lower()

    if memory_items:
        for item in memory_items:
            text += "\n" + str(item.get("summary", "")) + " " + str(item.get("content", ""))

    findings = []
    for pattern_name, pattern_info in SKILL_PATTERNS.items():
        keyword_hits = 0
        for kw in pattern_info["keywords"]:
            count = text.count(kw.lower())
            if count > 0:
                keyword_hits += count

        if keyword_hits >= 3:
            confidence = min(keyword_hits / 10, 0.95)
            findings.append({
                "pattern": pattern_name,
                "confidence": round(confidence, 2),
                "evidence_count": keyword_hits,
                "description": pattern_info["description"],
                "example": pattern_info["example"],
            })

    # 按置信度排序
    findings.sort(key=lambda x: x["confidence"], reverse=True)
    return findings


def generate_skill_md(
    pattern_name: str,
    description: str,
    example: str,
) -> str:
    """
    根据模式生成 SKILL.md 内容。

    Args:
        pattern_name: 模式名
        description: 技能描述
        example: 使用示例

    Returns:
        SKILL.md 格式的文本
    """
    skill_configs = {
        "paper-comparison": _generate_comparison_skill,
        "dataset-info": _generate_dataset_skill,
        "experiment-log": _generate_experiment_skill,
        "graph-explore": _generate_graph_skill,
        "arxiv-monitor": _generate_arxiv_skill,
        "code-search": _generate_code_skill,
    }

    generator = skill_configs.get(pattern_name, _generate_generic_skill)
    return generator(description, example)


def _generate_comparison_skill(desc: str, example: str) -> str:
    return f"""---
name: paper-comparison
description: {desc}
metadata: {{"akashic": {{"always": true, "requires": {{}}}}}}
---

# Skill: 论文方法对比

## 能力
- 对比多篇论文的方法、模型架构和在特定数据集上的指标
- 支持通过知识图谱查询方法间的关系链
- 自动生成对比表

## 工具
- `search_papers(query, top_k)` — 搜索相关论文
- `query_graph(type="method_comparison", query="{example.split("在")[-1].split("上")[0] if "在" in example else "DOTA"}", metric="mAP")` — 查询指标对比

## 使用示例
- "{example}"
- "对比一下 Soft Teacher 和 Unbiased Teacher 在 DOTA 上的 mAP"
- "DOTA 上表现最好的三个半监督方法是什么？"
"""


def _generate_dataset_skill(desc: str, example: str) -> str:
    return f"""---
name: dataset-info
description: {desc}
metadata: {{"akashic": {{"always": true, "requires": {{}}}}}}
---

# Skill: 数据集信息查询

## 能力
- 查询遥感目标检测数据集的类别、数量、标注方式
- 结合知识图谱查看哪些方法在该数据集上做过评估

## 工具
- `search_papers(query, top_k)` — 搜索涉及该数据集的论文
- `query_graph(type="method_comparison", query="DOTA", metric="mAP")` — 该数据集上的方法表现

## 使用示例
- "{example}"
- "DOTA-v1.0 和 DOTA-v1.5 有什么区别？"
- "哪些方法在 DIOR 上评估过？"
"""


def _generate_experiment_skill(desc: str, example: str) -> str:
    return f"""---
name: experiment-log
description: {desc}
metadata: {{"akashic": {{"always": true, "requires": {{}}}}}}
---

# Skill: 实验记录与跟踪

## 能力
- 创建实验并记录完整配置
- 记录主动学习每轮的结果（采样策略、queried 数、mAP）
- 对比多组实验的指标变化曲线

## 工具
- `create_experiment(name, config, description)` — 创建实验
- `track_al_round(experiment_id, round_number, metrics, sampling_strategy, queried_count)` — 记录轮次
- `compare_experiments(experiment_ids)` — 对比多组实验

## 使用示例
- "{example}"
- "创建实验 ResNet50 on DOTA 5% labeled"
- "第 3 轮主动学习 mAP 是多少？"
"""


def _generate_graph_skill(desc: str, example: str) -> str:
    return f"""---
name: graph-explore
description: {desc}
metadata: {{"akashic": {{"always": true, "requires": {{}}}}}}
---

# Skill: 知识图谱探索

## 能力
- 查询方法间的依赖关系和改进链
- 发现数据集上的方法生态
- 按研究方向（半监督/主动学习）筛选方法

## 工具
- `query_graph(type="methods_by_concept", query="active_learning")` — 按概念查方法
- `query_graph(type="method_comparison", query="DOTA", metric="mAP")` — 方法横向对比
- `query_graph(type="entity_search", query="")` — 搜索实体

## 使用示例
- "{example}"
- "哪些方法使用了不确定性采样？"
- "基于 Mean Teacher 的改进有哪些？"
"""


def _generate_arxiv_skill(desc: str, example: str) -> str:
    return f"""---
name: arxiv-monitor
description: {desc}
metadata: {{"akashic": {{"always": true, "requires": {{}}}}}}
---

# Skill: 最新论文查询

## 能力
- 查询最近 ArXiv 上相关领域的新论文
- 查看按研究方向分组的论文列表
- 获取论文的摘要和链接

## 工具
- `query_graph(type="entity_search", query="arxiv")` — 查询已摄入的最新论文
- `search_papers(query="remote sensing object detection 2024", top_k=5)` — 搜索最新论文

## 使用示例
- "{example}"
- "最近有没有半监督目标检测的新论文？"
- "主动学习方向最近有什么进展？"
"""


def _generate_code_skill(desc: str, example: str) -> str:
    return f"""---
name: code-search
description: {desc}
metadata: {{"akashic": {{"always": true, "requires": {{}}}}}}
---

# Skill: 开源代码查询

## 能力
- 查找论文的开源代码仓库
- 获取代码的 star 数、框架和许可证信息

## 工具
- `search_papers(query="method_name code github")` — 搜索包含代码链接的论文

## 使用示例
- "{example}"
- "ActiveTeacher 代码开源了吗？"
- "Soft Teacher 的官方实现在哪？"
"""


def _generate_generic_skill(desc: str, example: str) -> str:
    return f"""---
name: auto-skill-draft
description: {desc}
metadata: {{"akashic": {{"always": false, "requires": {{}}}}}}
---

# Skill: {desc[:20]}

## 能力
- 根据用户最近的高频请求自动生成

## 使用示例
- "{example}"

#quality: draft
"""