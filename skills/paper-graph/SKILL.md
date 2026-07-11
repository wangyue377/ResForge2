---
name: paper-graph
description: 查询论文知识图谱，获取方法/数据集/指标的关系网络
metadata: {"akashic": {"always": true, "requires": {}}}
---

# Skill: Paper Knowledge Graph

## 能力
- 使用 Neo4j 查询知识图谱中的论文实体关系
- 方法→数据集→指标的多跳关系追踪
- 自动生成方法对比表

## 工具
- `query_graph(type="method_comparison", query="DOTA", metric="mAP")` — 数据集上的方法指标对比
- `query_graph(type="methods_by_concept", query="uncertainty_sampling")` — 某概念相关的所有方法
- `query_graph(type="entity_search", query="ActiveTeacher")` — 搜索实体及其关系

## 使用示例
- "DOTA 上哪些半监督方法达到了最好的 mAP？"
- "有哪些方法使用了不确定性采样这个策略？"
- "帮我查一下 ActiveTeacher 这个方法的相关信息"
- "一致性正则化相关的方法有哪些？"
