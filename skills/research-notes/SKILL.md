---
name: research-notes
description: 查阅本地科研调研笔记，回答方法对比/技术演进类问题
metadata: {"akashic": {"always": true, "requires": {}}}
---

# Skill: Research Notes

## 能力
- 当用户问及方法对比、技术演进、基线关系时，优先查阅本地 `kb/` 目录下的调研笔记
- 支持跨文档关联阅读（如不同方法调研中的交叉引用）
- 结合调研笔记 + 知识图谱（Neo4j） + 论文搜索引擎，给出准确的方法对比回答

## 触发场景
用户提问涉及以下关键词时自动激活：
- 方法对比："对比 X 和 Y"、"X 和 Y 有什么区别"、"哪个更好"
- 技术演进："X 的后续工作"、"基于 X 的方法"、"X 有哪些改进"
- 数字指标："在 DOTA 上的 mAP"、"达到多少精度"
- 基线查询："X 的 baseline 是什么"、"X 和 Y 什么关系"

## 步骤
1. **查阅调研笔记**：先用 `read_file` 或 `glob` 搜索 `kb/` 目录下相关 `.md` 文件
   - 路径：`{workspace}/kb/*.md`
   - 匹配方法名（如 `soft_teacher`、`dense_teacher`）和相关概念
2. **交叉验证**：对笔记中的方法名、数字指标、引用关系，用 `search_papers` 或 `query_graph` 做二次确认
3. **回答**：基于笔记中的脉络梳理，用自然语言讲解方法关系链

## 工具
- `glob(pattern)` — 搜索 kb/ 目录下的调研笔记文件
- `read_file(path)` — 读取调研笔记全文
- `search_papers(query, top_k)` — 语义+关键词搜索论文库验证
- `query_graph(type, query, metric)` — 知识图谱查询实体关系

## 现有笔记
| 文件 | 内容 | 关键词 |
|------|------|--------|
| `kb/soft_teacher_survey.md` | Soft Teacher 系列方法演进（~20 篇） | soft teacher, semi-detr, dense teacher, focal teacher, mcl, sood |

## 使用示例
- "Soft Teacher 有哪些后续方法？它们的演进关系是什么？"
- "在 DOTA 上最高的半监督检测方法是什么，mAP 多少？"
- "对比一下 Dense Teacher 和 Focal Teacher 的区别"
- "半监督目标检测有哪些不同的技术路线？"

## 注意事项
- 先读笔记再查知识图谱，笔记是脉络梳理，图谱做数字验证
- 笔记中的数字可能不是最新的，引用时用 `search_papers` 或 `query_graph` 核实
- 方法全称和缩写都要覆盖搜索（如 "Soft Teacher" 和 "soft_teacher"）