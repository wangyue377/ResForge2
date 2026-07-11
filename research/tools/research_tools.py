"""
Agent 工具定义 — 科研助手功能入口

这些工具注册到 Agent 的 ToolRegistry 中，让 LLM 可以调用。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent.tools.base import Tool

logger = logging.getLogger(__name__)


class IngestPaperTool(Tool):
    """从 ArXiv 链接或本地文件导入论文到科研知识库"""

    name = "ingest_paper"
    description = (
        "从 ArXiv 链接/ID 或本地文件导入论文到个人科研知识库。"
        "支持 arxiv（自动下载）、或本地文件（自动识别 PDF/Word/Excel/PPT/文本等格式）。"
        "自动提取元数据、按章节分块、向量化索引，并在后台构建知识图谱。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "论文来源：ArXiv ID（如 2401.12345）、ArXiv URL、或本地文件路径",
            },
            "source_type": {
                "type": "string",
                "enum": ["arxiv", "file"],
                "description": "来源类型：arxiv（从网络下载，需 ArXiv ID/URL）或 file（本地文件，自动识别格式）",
            },
        },
        "required": ["source", "source_type"],
    }

    def __init__(self, pipeline: Any, db: Any, **kwargs):
        super().__init__(**kwargs)
        self.pipeline = pipeline
        self.db = db

    async def execute(self, **kwargs) -> str:
        source = kwargs["source"]
        source_type = kwargs["source_type"]

        try:
            if source_type == "arxiv":
                paper_id = await self.pipeline.ingest_from_arxiv(source)
            else:
                paper_id = await self.pipeline.ingest_from_file(source)

            from sqlalchemy import text
            async with self.db.get_session() as session:
                row = (await session.execute(
                    text("""
                        SELECT title, arxiv_id,
                            (SELECT count(*) FROM paper_chunks WHERE paper_id=:pid) AS chunk_count
                        FROM papers WHERE id=:pid
                    """),
                    {"pid": paper_id},
                )).fetchone()

            if row:
                return (
                    f"✅ 论文摄入成功！\n\n"
                    f"📄 **{row[0]}**\n"
                    f"📊 共 {row[2]} 个文本块已索引\n"
                    f"🔮 后台正在构建知识图谱..."
                )
            return f"✅ 论文摄入完成，ID: {paper_id}"

        except Exception as e:
            logger.error("Ingest failed: %s", e)
            return f"❌ 论文摄入失败: {e}"


class SearchPapersTool(Tool):
    """在科研知识库或网络中搜索论文，支持多源融合"""

    name = "search_papers"
    description = (
        "搜索论文，支持本地知识库（已导入论文的语义+关键词融合检索）"
        "和网络搜索（ArXiv + Semantic Scholar + OpenAlex + DBLP 四源并行）。"
        "返回最相关的论文列表。适合查文献、找方法、做调研。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，如 'uncertainty sampling remote sensing DOTA' 或 '半监督目标检测'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数（默认 8，最大 20）",
                "minimum": 1,
                "maximum": 20,
            },
            "source": {
                "type": "string",
                "enum": ["local", "web", "all"],
                "description": "搜索范围：local（本地知识库）、web（四源网络搜索）、all（两者都搜并融合）",
            },
        },
        "required": ["query"],
    }

    def __init__(
        self,
        vector_retriever: Any,
        keyword_retriever: Any,
        graphrag_retriever: Any,
        embedder: Any,
        fusion: Any,
        web_searcher: Any = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.vector = vector_retriever
        self.keyword = keyword_retriever
        self.graphrag = graphrag_retriever
        self.embedder = embedder
        self.fusion = fusion
        self.web_searcher = web_searcher

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        top_k = int(kwargs.get("top_k", 8))
        source = kwargs.get("source", "local")

        lines = [f"## 搜索结果: {query}\n"]

        # 本地搜索
        local_results = []
        if source in ("local", "all"):
            local_results = await self._search_local(query, top_k)

        # 网络搜索
        web_results = []
        if source in ("web", "all") and self.web_searcher:
            web_results = await self._search_web(query, top_k)

        if source == "all":
            results = self._merge_results(local_results, web_results, top_k)
        elif source == "web":
            results = web_results
        else:
            results = local_results

        if not results:
            return self._empty_result(source)

        for i, r in enumerate(results, 1):
            lines.append(self._format_result(i, r))

        return "\n".join(lines)

    async def _search_local(self, query: str, top_k: int) -> list[dict]:
        """本地知识库搜索（现有逻辑）"""
        try:
            query_emb = await self.embedder.embed_text(query)
            vector_results = await self.vector.search_chunks(query_emb, top_k=top_k * 2)
            keyword_results = await self.keyword.search_chunks(query, top_k=top_k * 2)
            fused = self.fusion.fuse(vector_results, keyword_results)
            top_results = fused[:top_k]

            graph_context = ""
            if self.graphrag:
                try:
                    graph_context = await self.graphrag.format_entity_context(
                        query, max_entities=3
                    )
                except Exception:
                    pass

            result_list = []
            for r in top_results:
                result_list.append({
                    "type": "local",
                    "title": r.get("paper_title", "Unknown"),
                    "score": r.get("fusion_score", r.get("score", 0)),
                    "section": r.get("section", ""),
                    "content": r.get("content", "")[:200],
                    "arxiv_id": r.get("arxiv_id", ""),
                    "graph_context": graph_context,
                })
            return result_list
        except Exception as e:
            logger.error("Local search failed: %s", e)
            return []

    async def _search_web(self, query: str, top_k: int) -> list[dict]:
        """四源网络搜索"""
        try:
            results = await self.web_searcher.search(query, top_k=top_k)
            result_list = []
            for r in results:
                result_list.append({
                    "type": "web",
                    "source": r.source,
                    "title": r.title,
                    "authors": r.authors,
                    "abstract": r.abstract[:200] if r.abstract else "",
                    "url": r.url,
                    "arxiv_id": r.arxiv_id,
                    "citation_count": r.citation_count,
                    "published_date": r.published_date,
                    "score": 1.0,
                })
            return result_list[:top_k]
        except Exception as e:
            logger.error("Web search failed: %s", e)
            return []

    def _merge_results(self, local: list[dict], web: list[dict], top_k: int) -> list[dict]:
        """本地+网络融合（本地优先）"""
        seen_titles = set()
        merged = []
        for r in local + web:
            t = r.get("title", "").lower().strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                merged.append(r)
        return merged[:top_k]

    def _format_result(self, i: int, r: dict) -> str:
        if r.get("type") == "web":
            source_tag = r.get("source", "web")
            authors = ", ".join(r.get("authors", [])[:3])
            cite = f" | 引用: {r['citation_count']}" if r.get("citation_count") else ""
            date = f" | {r.get('published_date', '')[:10]}" if r.get("published_date") else ""
            return (
                f"**{i}. [🌐 {source_tag}] {r['title'][:80]}**\n"
                f"   作者: {authors}{cite}{date}\n"
                f"   > {r.get('abstract', '')[:200]}...\n"
                f"   🔗 {r.get('url', '')}\n"
            )
        else:
            title = r.get("title", "Unknown")[:80]
            score = r.get("score", 0)
            section = r.get("section", "")
            content = r.get("content", "")
            lines = [
                f"**{i}. [{title}]({r.get('arxiv_id', '')})** (相关度: {score:.3f})\n"
            ]
            if section:
                lines.append(f"   章节: {section}\n")
            if content:
                lines.append(f"   > {content}...\n")
            return "".join(lines)

    def _empty_result(self, source: str) -> str:
        if source == "local":
            return "本地知识库未找到相关结果。可以尝试：\n1. 用 `ingest_paper` 导入相关论文\n2. 加 `source=web` 参数搜网络\n3. 修改搜索词重试"
        if source == "web":
            return "网络搜索未找到相关结果。请修改搜索词重试。"
        return "本地和网络均未找到相关结果。"


class PaperDetailTool(Tool):
    """获取论文详细信息（引用数、代码仓库等）"""

    name = "paper_detail"
    description = (
        "通过 ArXiv ID 获取论文的详细信息，包括引用数、代码仓库链接、发表会议/期刊等。"
        "数据来源：Semantic Scholar + GitHub。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "arxiv_id": {
                "type": "string",
                "description": "ArXiv ID，如 2401.12345",
            },
        },
        "required": ["arxiv_id"],
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def execute(self, **kwargs) -> str:
        arxiv_id = kwargs["arxiv_id"]
        parts = [f"## 论文详情: {arxiv_id}\n"]

        # Semantic Scholar 查引用
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/ArXiv:{arxiv_id}",
                    params={"fields": "title,citationCount,publicationVenue,venue"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    parts.append(f"📄 标题: {data.get('title', 'N/A')}")
                    parts.append(f"📊 引用数: {data.get('citationCount', 'N/A')}")
                    venue = data.get("venue") or ""
                    if venue:
                        parts.append(f"🏛 发表: {venue}")
                else:
                    parts.append("Semantic Scholar 未找到该论文。")
        except Exception as e:
            parts.append(f"⚠ 查询引用信息失败: {e}")

        # GitHub 查代码
        try:
            from research.search.code_search import find_code_for_paper
            code_url = await find_code_for_paper(arxiv_id)
            if code_url:
                parts.append(f"💻 代码: {code_url}")
        except Exception:
            pass

        parts.append(f"\n🔗 https://arxiv.org/abs/{arxiv_id}")
        return "\n".join(parts)


class CodeLookupTool(Tool):
    """搜索论文的官方代码实现"""

    name = "code_lookup"
    description = "搜索论文的官方代码实现（GitHub），通过论文标题或 ArXiv ID 查找。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "论文标题或 ArXiv ID",
            },
        },
        "required": ["query"],
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        try:
            from research.search.code_search import find_code_for_paper, search_github_by_title
            # 先试 ArXiv ID
            import re
            arxiv_match = re.search(r"(\d{4}\.\d{4,5})", query)
            if arxiv_match:
                code_url = await find_code_for_paper(arxiv_match.group(1))
                if code_url:
                    return f"## 代码查找结果\n\n📦 **{query}**\n💻 {code_url}"

            # 按标题搜 GitHub
            results = await search_github_by_title(query, top_k=5)
            if not results:
                return f"未找到 '{query}' 的代码实现。可以尝试：\n1. 在 https://paperswithcode.com 手动搜索\n2. 使用更精确的论文标题"

            lines = [f"## 代码查找结果: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r['repo']}]({r['url']}) — {r.get('description', '')[:100]}")
                if r.get("stars"):
                    lines.append(f"   ⭐ {r['stars']} stars")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 代码查找失败: {e}"


class SummarizePaperTool(Tool):
    """快速总结论文内容"""

    name = "summarize_paper"
    description = "从论文链接或本地 PDF 路径快速总结论文核心内容（问题、方法、实验结论）。"
    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "ArXiv ID、ArXiv URL、或本地文件路径",
            },
        },
        "required": ["source"],
    }

    def __init__(self, llm_provider: Any = None, pipeline: Any = None, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm_provider
        self.pipeline = pipeline

    async def execute(self, **kwargs) -> str:
        source = kwargs["source"]
        text = ""

        # 判断是 ArXiv ID/URL 还是本地文件
        import re
        arxiv_match = re.search(r"(\d{4}\.\d{4,5})", source)

        try:
            if arxiv_match:
                # 从 ArXiv 获取摘要
                arxiv_id = arxiv_match.group(1)
                from research.ingestion.arxiv_loader import ArxivLoader
                loader = ArxivLoader()
                meta = await loader.fetch_by_id(arxiv_id)
                text = f"Title: {meta['title']}\nAuthors: {', '.join(meta['authors'])}\nAbstract: {meta['abstract']}"
            else:
                # 从本地文件提取文本
                if self.pipeline:
                    text = await self.pipeline.extract_text_from_file(source)
                else:
                    from research.ingestion.doc_parser import DocumentParser
                    parser = DocumentParser()
                    text = parser.parse(source)

            if not text:
                return "❌ 无法获取论文文本。"
        except Exception as e:
            return f"❌ 读取论文失败: {e}"

        # LLM 总结
        if not self.llm:
            return f"## 论文内容\n\n{text[:1000]}..." if len(text) > 1000 else f"## 论文内容\n\n{text}"

        prompt = f"""请总结以下论文，格式如下：

## 研究问题
（一句话说明要解决什么问题）

## 方法
（核心方法思路，1-2 句话）

## 实验结论
（关键实验结果和发现）

## 贡献
（主要贡献点）

论文内容:
{text[:3000]}"""

        try:
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            content = response["choices"][0]["message"]["content"]
            return f"## 📄 论文总结\n\n{content}"
        except Exception as e:
            return f"❌ 总结失败: {e}\n\n原始文本:\n{text[:500]}..."


class LatexFormatTool(Tool):
    """生成 BibTeX 引用格式"""

    name = "latex_format"
    description = "生成论文的 BibTeX 引用格式，支持 ArXiv ID、DOI 或论文标题搜索。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "ArXiv ID（如 2401.12345）、DOI、或论文标题",
            },
        },
        "required": ["query"],
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]

        import re
        import httpx

        # 尝试从 Semantic Scholar 获取元数据
        arxiv_match = re.search(r"(\d{4}\.\d{4,5})", query)
        paper_id = f"ArXiv:{arxiv_match.group(1)}" if arxiv_match else query

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}",
                    params={"fields": "title,authors,year,venue,externalIds"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "Unknown")
                    authors = [a.get("name", "") for a in (data.get("authors") or [])]
                    year = data.get("year", "")
                    venue = data.get("venue", "")
                    ext_ids = data.get("externalIds") or {}
                    arxiv_id = ext_ids.get("ArXiv", arxiv_match.group(1) if arxiv_match else "")
                    doi = ext_ids.get("DOI", "")

                    bibkey = arxiv_id.replace(".", "_") if arxiv_id else "paper"

                    author_str = " and ".join(authors)
                    bibtex = f"@article{{{bibkey},\n"
                    bibtex += f"  author = {{{author_str}}},\n"
                    bibtex += f"  title = {{{title}}},\n"
                    if year:
                        bibtex += f"  year = {{{year}}},\n"
                    if venue:
                        bibtex += f"  journal = {{{venue}}},\n"
                    if arxiv_id:
                        bibtex += f"  eprint = {{{arxiv_id}}},\n"
                        bibtex += f"  archivePrefix = {{arXiv}},\n"
                    if doi:
                        bibtex += f"  doi = {{{doi}}},\n"
                    bibtex += "}"

                    # 同时也显示 readable 版本
                    readable = (
                        f"{', '.join(authors[:5])}{' et al.' if len(authors) > 5 else ''}"
                        f" ({year}). {title}."
                    )
                    if venue:
                        readable += f" {venue}."
                    return f"## BibTeX 引用\n\n```bibtex\n{bibtex}\n```\n\n**文内引用:**\n{readable}"

            return "❌ 未找到该论文信息，请检查输入是否正确。"
        except Exception as e:
            return f"❌ BibTeX 生成失败: {e}"


class QueryGraphTool(Tool):
    """查询论文知识图谱，获取方法/数据集/指标的关系网络"""

    name = "query_graph"
    description = (
        "查询论文知识图谱（Neo4j），获取方法、数据集、指标之间的实体关系网络。"
        "支持方法关系查询、数据集对比、概念搜索、实体模糊搜索四种模式。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["method_comparison", "methods_by_concept", "entity_search", "method_relations"],
                "description": "查询类型：method_comparison（数据集上的方法指标对比）、methods_by_concept（某概念相关的所有方法）、entity_search（实体关键词搜索）、method_relations（某方法的关系网络）",
            },
            "query": {
                "type": "string",
                "description": "查询关键词，如方法名（ActiveTeacher）、数据集名（DOTA）、概念名（uncertainty_sampling）",
            },
            "metric": {
                "type": "string",
                "description": "指标名（仅 method_comparison 类型使用，默认 mAP）",
            },
        },
        "required": ["type", "query"],
    }

    def __init__(self, graphrag: Any, **kwargs):
        super().__init__(**kwargs)
        self.graphrag = graphrag

    async def execute(self, **kwargs) -> str:
        qtype = kwargs["type"]
        query = kwargs["query"]
        metric = kwargs.get("metric", "mAP")

        if not self.graphrag:
            return "❌ 知识图谱未连接。请确保 Neo4j 已启动（docker compose -f docker/docker-compose.research.yml up -d）。"

        try:
            if qtype == "method_comparison":
                return await self.graphrag.format_method_comparison(query, metric)

            elif qtype == "methods_by_concept":
                results = await self.graphrag.get_methods_by_concept(query)
                if not results:
                    return f"（知识图谱中未找到与概念「{query}」相关的方法）"
                lines = [f"## 与「{query}」相关的方法\n"]
                for r in results:
                    method = r.get("method", "?")
                    papers = r.get("papers", [])
                    datasets = r.get("datasets", [])
                    lines.append(f"- **{method}**")
                    if papers:
                        lines.append(f"  - 论文: {', '.join(papers[:3])}")
                    if datasets:
                        lines.append(f"  - 数据集: {', '.join(datasets[:3])}")
                return "\n".join(lines)

            elif qtype == "entity_search":
                results = await self.graphrag.search_entities(query)
                if not results:
                    return f"（知识图谱中未找到与「{query}」相关的实体）"
                lines = [f"## 实体搜索: {query}\n"]
                for r in results:
                    name = r.get("name", "")
                    etype = r.get("type", "")
                    desc = r.get("description", "")
                    lines.append(f"- **{name}** ({etype}): {desc[:100]}")
                return "\n".join(lines)

            elif qtype == "method_relations":
                results = await self.graphrag.search_by_method(query)
                if not results:
                    return f"（知识图谱中未找到方法「{query}」的关系）"
                lines = [f"## 方法「{query}」的关系网络\n"]
                for r in results:
                    rel = r.get("relation", "")
                    target = r.get("target", "")
                    target_type = r.get("target_type", "")
                    lines.append(f"- [{rel}] → **{target}** ({target_type})")
                return "\n".join(lines)

            else:
                return f"❌ 未知查询类型: {qtype}，支持: method_comparison, methods_by_concept, entity_search, method_relations"

        except Exception as e:
            logger.error("QueryGraph failed: %s", e)
            return f"❌ 知识图谱查询失败: {e}"
