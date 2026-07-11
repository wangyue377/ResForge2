# Hy3 Research Assistant

**Resolves:** [issue#4](https://github.com/Tencent-Hunyuan/Hy3/tree/rhinobird2026)

> 基于 **腾讯混元 Hy3** 的个人深度研究助手 — 论文摄入、多源搜索、知识图谱、自动总结与引用生成。
>
> 🧬 全程通过 Hy3 API 驱动，不做训练 / 微调 / 本地推理部署。
> 🧑‍💻 项目由 CodeBuddy 协作完成（vibe-coded）。
> 📦 为 [2026 犀牛鸟开源人才培养活动](https://github.com/Tencent-Hunyuan/Hy3/tree/rhinobird2026) 提交。

---

## 项目简介

**Hy3 Research Assistant** 是一个面向科研场景的个人深度研究助手，面向论文阅读、文献调研、知识管理场景。

用户可以输入论文 PDF、ArXiv ID 或搜索关键词，系统会基于 Hy3 自动完成论文摄入、语义分块、向量化索引、知识图谱构建、多源文献搜索、论文总结和引用生成等完整科研工作流。

本项目不是简单聊天机器人，而是围绕科研工作流设计的**端到端论文知识管理 Copilot**，帮助研究人员从"拿到一篇论文"到"生成调研报告"全流程提效。

---

## Hy3 在系统中承担的角色

系统中**所有 LLM 调用**均由 Hy3 完成：

| 角色 | 模型 | 用途 |
|------|------|------|
| **主模型** | `hy3 (TokenHub)` | 论文总结、工具调用决策、搜索融合、引用生成、代码查找 |
| **嵌入模型** | `kinfra-text-embedding-0.6b (TokenHub)` | 论文向量化（1024 维）、语义检索（TokenHub 配套服务） |

No other LLM or embedding provider is used. 全程通过 TokenHub（Hy3 配套服务）API 调用。

---

## 快速启动

### 前置条件

- Python 3.12+
- Docker（用于 PostgreSQL + Neo4j + Redis）
- Hy3 API Key（写入 `config.toml`）

### 安装

```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd ResForge2

# 2. 创建独立虚拟环境并安装依赖（uv 形式，环境位于项目根目录 .venv）
uv venv && uv pip install -r requirements.txt
uv pip install python-docx python-pptx openpyxl

# 3. 配置 Hy3 API Key（写入 config.toml 的 [llm.main] 和 [llm.fast] 字段）

# 4. 启动数据库
docker compose -f docker/docker-compose.research.yml up -d

# 5. 启动 Agent
uv run python main.py
# 启动完整服务后，浏览器打开 http://localhost:2236/chat 即可与 AI 助手对话

# 6. （可选）打开 Dashboard
uv run python main.py dashboard
```

### 工作区（记忆与技能文件存放目录）

Agent 的记忆文件（`memory/`）、技能文件（`skills/`）、会话库、图谱库等全部存放在**工作区目录**中，默认路径为：

```
~/.ResForge2
```

- 该目录已与项目代码分离，可单独备份 / 迁移。
- 若需使用其他路径，启动时通过 `--workspace` 指定即可：

  ```bash
  uv run python main.py --workspace /your/path/ResForge2
  ```

- 首次使用需初始化工作区（创建上述目录与本地数据库）：

  ```bash
  uv run python main.py init
  ```

---

## Demo 演示

### Demo 1：论文摄入 → 自动总结 → 生成引用

```
用户: 帮我把这个 PDF 导进去，顺便总结下它讲了啥：C:\path\to\sood-mcl.pdf
  → Hy3 读取本地 PDF，自动提取元数据、分块、向量化
  → 存入 PostgreSQL + 构建 Neo4j 知识图谱

用户: 给我这篇论文的引用格式，要 BibTeX 那种
  → Hy3 通过 Semantic Scholar API 获取论文信息
  → 生成 BibTeX 引用格式
```

### Demo 2：四源论文搜索 → 代码查找

```
用户: 帮我找找关于半监督目标检测的论文，联网搜一下
  → 四源并行搜索（ArXiv + Semantic Scholar + OpenAlex + DBLP）
  → Hy3 融合排序、去重
  → 返回带引用数和代码链接的结果

用户: 这篇 sood-mcl.pdf 有官方代码实现吗？
  → 搜索 GitHub + PapersWithCode
  → 返回论文官方代码仓库
```

### Demo 3：论文知识库 + 知识图谱问答

> 前面摄入的论文已沉淀进**向量知识库（PostgreSQL + pgvector）**与**实体关系图谱（Neo4j）**，可直接对话式检索与推理。

```
用户: 我导进去的这些论文里，哪些用了 Soft Teacher 框架？它们之间啥关系？
  → Hy3 在向量知识库里做语义检索（向量 + 关键词 + 图谱三通道 RRF 融合）
  → 再从 Neo4j 拉出「方法 / 数据集 / 指标」实体关系
  → 返回相关论文清单 + 关系说明（谁基于谁、用了啥数据集、指标如何对比）

用户: 帮我把已经存好的、关于"主动学习"的工作整理一下，顺手画个方法对比关系图
  → 知识库语义检索聚合同主题论文
  → 知识图谱抽取各方法的上下游依赖与方法对比
  → 生成综述要点 + 方法演进/对比关系图
```

[📺 点此观看演示 GIF](media/demo/demo.gif)（需安装 [Git LFS](https://git-lfs.com/) 后 `git lfs pull` 才能本地查看）

---

## 功能矩阵

| 功能 | 说明 | 使用方法 |
|------|------|---------|
| **论文摄入** | 从 ArXiv 或本地文件导入，自动提取元数据、分块索引。支持 PDF/Word/Excel/PPT/文本等 28+ 格式 | `ingest_paper("2401.12345", "arxiv")` 或 `ingest_paper("paper.docx", "file")` |
| **语义搜索** | 本地三通道融合检索（向量 + 关键词 + 知识图谱）或四源网络搜索（ArXiv + Semantic Scholar + OpenAlex + DBLP） | `search_papers("uncertainty sampling")` |
| **网络搜索** | 四源并行搜索，结果去重融合排序 | 加 `source="web"` 或 `source="all"` |
| **论文详情** | 引用数、代码仓库、发表会议查询 | `paper_detail(arxiv_id="2401.12345")` |
| **代码查找** | 按论文标题或 ArXiv ID 搜索 GitHub 实现 | `code_lookup(query="2401.12345")` |
| **论文总结** | Hy3 快速总结论文核心内容 | `summarize_paper(source="2401.12345")` |
| **BibTeX** | 生成论文引用格式 | `latex_format(query="2401.12345")` |
| **知识图谱** | 自动提取方法/数据集/指标实体关系，Neo4j 存储 | `query_graph(type="method_comparison", query="DOTA")` |
| **实验跟踪** | 记录实验配置和主动学习轮次 | `create_experiment(name="...", config={...})` |
| **Web Chat** | 浏览器端对话界面，支持 Markdown 渲染和打字机效果 | `python main.py` → [http://localhost:2236/chat](http://localhost:2236/chat) |
| **Dashboard** | 论文/实验/图谱可视化看板 | `python main.py dashboard` → [http://localhost:2236](http://localhost:2236) |

---

## 已完成内容

- ✅ 基于 Hy3 的 Agent 核心框架（6 阶段推理管道）
- ✅ 论文摄入管道（ArXiv / 本地 PDF / 28 种文件格式）
- ✅ 语义分块 + 向量化索引（pgvector 1024 维）
- ✅ 多源论文搜索（ArXiv + Semantic Scholar + OpenAlex + DBLP + Web）
- ✅ 本地三通道融合检索（向量 + 关键词 + 知识图谱）
- ✅ 多格式文档解析（PDF / Word / Excel / PPT / 文本）
- ✅ LLM 辅助元数据提取（标题 / 作者 / 摘要）
- ✅ Neo4j 知识图谱构建与方法实体关系抽取
- ✅ 论文总结 + BibTeX 引用生成 + 代码仓库查找
- ✅ 实验记录与跟踪
- ✅ **Web Chat** 浏览器端交互界面（支持 Markdown 渲染）
- ✅ **Dashboard** 论文 / 实验 / 图谱可视化看板
- ✅ 查询预处理 + 年份范围过滤
- ✅ 全文 Hy3 / TokenHub 体系（无第三方模型）

## 项目结构

```
ResForge2/
├── main.py                     # 主入口
├── config.toml                 # 配置文件（Hy3 API Key 等）
├── bootstrap/                  # 应用编排
│   ├── app.py                  #   AppRuntime 主调度器
│   ├── dashboard_api.py        #   FastAPI 仪表盘
│   ├── tools.py                #   工具注册与 CoreRuntime
│   └── toolsets/               #   工具集提供者
├── agent/                      # Agent 核心引擎
│   ├── core/                   #   推理管道、提示构建
│   ├── looping/                #   事件循环、中断控制
│   ├── tools/                  #   工具注册、文件系统、搜索
│   ├── provider.py             #   Hy3 API 调用封装
│   └── config.py               #   配置加载
├── research/                   # 科研子系统
│   ├── ingestion/              #   论文摄入管道（解析/分块/嵌入）
│   ├── search/                 #   多源搜索（ArXiv/SS/OA/DBLP/Web）
│   ├── retrieval/              #   向量/关键词/图谱融合检索
│   ├── graph/                  #   Neo4j 知识图谱
│   ├── tools/                  #   7 个科研工具
│   └── models/                 #   数据库模型
├── plugins/research/           # 科研插件入口
├── infra/                      # 基础设施
│   ├── channels/               #   通信渠道（CLI / Telegram / QQ）
│   └── providers/              #   LLM 提供者适配器
├── frontend/dashboard/         # Dashboard 前端源码
├── static/                     # 编译后静态资源
│   ├── dashboard/              #   Dashboard SPA
│   └── chat/                   #   Web Chat 界面
├── docker/                     # Docker 编排（PostgreSQL/Neo4j/Redis）
├── skills/                     # 技能定义文件
└── media/demo/                 # 演示 GIF
```

## CodeBuddy 协作记录

本项目完全通过 CodeBuddy / Claude Code 协作完成（vibe-coding）。以下是 AI 自动生成的代码模块：

| 模块 | 文件 | AI 角色 |
|------|------|---------|
| 多源搜索 | `research/search/*.py` | 编写全部 5 个文件（PaperSearcher + 4 源适配器） |
| 多格式文档解析 | `research/ingestion/doc_parser.py` | 编写 28 格式路由和解析器 |
| 论文工具 | `research/tools/research_tools.py` | 编写 7 个工具类 |
| 知识图谱写入修复 | `research/graph/writer.py` | 修复 Cypher 属性名转义 |
| Feishu/SS/OA/DBLP MCP | `research/proactive/*_mcp_server.py` | 编写 4 个 MCP Server |
| README | `README.md` | 本文档 |

## 系统架构

```
消息通道（CLI / Web Chat / Telegram / QQ）
    → Agent 核心（6 阶段管道）
        → 工具系统（7 个科研工具）
            → Hy3 API（所有 LLM 调用）
        → 记忆系统（Markdown + sqlite-vec 双轨）
        → 检索系统（三通道 RRF 融合）

科研子系统（独立于 Agent 核心）
    ├── 论文摄入（ArXiv / 28 种文件格式）
    ├── 多源搜索（ArXiv + SS + OpenAlex + DBLP）
    ├── 知识图谱（PostgreSQL + pgvector + Neo4j）
    ├── Web Chat（FastAPI :2236/chat）
    ├── Dashboard（FastAPI :2236）
    └── 实验跟踪（PostgreSQL）
```

### 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| LLM | **Hy3 API** (腾讯混元) | 所有推理、总结、搜索决策 |
| 主数据库 | PostgreSQL 16 + pgvector | 论文元数据、向量检索 |
| 知识图谱 | Neo4j 5 | 实体关系存储、GraphRAG |
| 缓存 | Redis 7 | 论文缓存、任务去重 |
| 对话记忆 | SQLite + sqlite-vec | 语义记忆检索 |
| 文档解析 | PyMuPDF / python-docx / openpyxl / python-pptx | 28 种格式 |
| 搜索源 | ArXiv / Semantic Scholar / OpenAlex / DBLP | 四源并行 |

---

## 后续计划

- [ ] 增加 GitHub Issue / PR 自动解析与任务拆解
- [ ] 增加一键导出论文调研报告（Markdown / PDF）
- [ ] 增加浏览器插件（一键收藏论文到知识库）
- [ ] 增加论文订阅与自动摄入（RSS / ArXiv 监控）
- [ ] 增加多轮项目优化与 PR 提交前检查
- [ ] 增加 Demo GIF 或短视频演示

---

## 犀牛鸟活动信息

- **活动**：2026 犀牛鸟开源人才培养活动
- **Issue**：[Build a vibe-coded application powered by Hy3](https://github.com/Tencent-Hunyuan/Hy3/tree/rhinobird2026)
- **分支**：`rhinobird2026`
- **提交方式**：向 Hybrid 仓库的 `rhinobird2026` 分支提交 PR
- **认领时间**：2026 年 7 月 1 日～7 月 31 日

---

## License

Apache 2.0