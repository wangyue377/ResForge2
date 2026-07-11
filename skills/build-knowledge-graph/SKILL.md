---
name: build-knowledge-graph
description: 后台构建论文知识图谱：从最近摄入的论文中提取实体关系写入 Neo4j
metadata: {"akashic": {"always": false, "requires": {}}}
---

# Skill: Build Knowledge Graph

## 步骤
1. 查询 research_assistant.papers 中 status='indexed' 且图谱未构建的论文
2. 取每篇论文的所有文本块
3. 调用 GraphExtractor 批量提取实体（方法/数据集/指标/架构/概念）和关系
4. 调用 GraphWriter 写入 Neo4j（MERGE 去重）
5. 标记论文图谱状态为 completed

## 工具
- ingest_paper — 确保论文已摄入并索引
- search_papers — 验证图谱检索效果
- query_graph — 在线查询图谱

## 输出
- Neo4j 节点标签: Paper, Method, Dataset, Architecture, Metric, Concept
- Neo4j 关系类型: PROPOSES, USES, ACHIEVES, COMPOSED_OF, BASED_ON
