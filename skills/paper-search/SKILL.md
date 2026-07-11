---
name: paper-search
description: 在科研知识库中搜索论文，支持语义和关键词混合检索
metadata: {"akashic": {"always": true, "requires": {}}}
---

# Skill: Paper Search

## 能力
- 在 PostgreSQL + pgvector 论文知识库中搜索
- 支持语义搜索（向量相似度）和关键词全文搜索（BM25）
- 自动融合排序（RRF 算法）
- 结合知识图谱返回方法和数据集的关系

## 工具
- `search_papers(query, top_k)` — 语义+关键词融合搜索论文
- `query_graph(type, query, metric)` — 查询知识图谱

## 使用示例
- "找一下关于 uncertainty sampling 在遥感检测上的论文"
- "搜索在 DOTA 上评估的半监督方法"
- "对比 Soft Teacher 和 Unbiased Teacher 在 DIOR 上的结果"
- "有哪些方法使用了 consistency regularization 概念？"

## 注意事项
- 搜索前先用 ingest_paper 导入论文到知识库
- 搜索不到结果时，可以尝试换同义词或英文搜索
