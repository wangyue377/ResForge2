from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from proactive_v2.config import ProactiveConfig


@dataclass
class TelegramChannelConfig:
    token: str
    allow_from: list[str] = field(default_factory=list)
    channel_name: str = "telegram"


@dataclass
class QQGroupConfig:
    group_id: str
    allow_from: list[str] = field(default_factory=list)
    require_at: bool = True


@dataclass
class QQChannelConfig:
    bot_uin: str
    allow_from: list[str] = field(default_factory=list)
    groups: list[QQGroupConfig] = field(default_factory=list)
    websocket_open_timeout_seconds: float = 5.0


@dataclass
class QQBotGroupConfig:
    group_openid: str
    allow_from: list[str] = field(default_factory=list)
    require_at: bool = True
    allow_proactive: bool = False


@dataclass
class QQBotChannelConfig:
    app_id: str
    client_secret: str
    allow_from: list[str] = field(default_factory=list)
    groups: list[QQBotGroupConfig] = field(default_factory=list)


@dataclass
class ChannelsConfig:
    telegram: TelegramChannelConfig | None = None
    qq: QQChannelConfig | None = None
    qqbot: QQBotChannelConfig | None = None
    socket: str = "/tmp/resforge.sock"
    cli_session_key: str = ""


@dataclass
class MemoryEmbeddingConfig:
    model: str = "text-embedding-v3"
    api_key: str = ""
    base_url: str = ""


@dataclass
class MemoryConfig:
    enabled: bool = False
    engine: str = ""
    embedding: MemoryEmbeddingConfig = field(default_factory=MemoryEmbeddingConfig)


@dataclass
class FitbitIntegrationConfig:
    enabled: bool = False


@dataclass
class PeerAgentConfig:
    name: str
    base_url: str
    launcher: list[str]          # 拉起命令，如 ["uv", "run", "python", "-m", "app.a2a_server"]
    cwd: str | None = None       # 子进程工作目录，None 表示继承父进程
    description: str = ""        # 工具描述，用于 LLM 路由；服务器在线时会被 AgentCard 覆盖
    health_path: str = "/health"
    startup_timeout_s: int = 30
    shutdown_timeout_s: int = 10


@dataclass
class ResearchDatabaseConfig:
    type: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    db: str = "research_assistant"
    user: str = "research"
    password: str = "research_pass"
    pool_size: int = 10
    max_overflow: int = 5


@dataclass
class ResearchGraphConfig:
    type: str = "neo4j"
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "research_graph"


@dataclass
class ResearchCacheConfig:
    type: str = "redis"
    host: str = "localhost"
    port: int = 6379
    db: int = 0


@dataclass
class ResearchParsingConfig:
    pdf_engine: str = "pymupdf"
    chunk_strategy: str = "semantic"
    chunk_size: int = 512
    chunk_overlap: int = 64


@dataclass
class ResearchArxivConfig:
    enabled: bool = False
    categories: tuple[str, ...] = ("cs.CV", "cs.AI")
    max_results: int = 50
    poll_interval_minutes: int = 60
    relevance_threshold: float = 0.6


@dataclass
class ResearchEmbeddingConfig:
    model: str = "text-embedding-v3"
    dimension: int = 1024
    api_key: str = ""
    base_url: str = ""


@dataclass
class ResearchExperimentConfig:
    tracking_enabled: bool = True


@dataclass
class ResearchSearchConfig:
    """多源搜索配置"""
    enabled: bool = True
    arxiv_enabled: bool = True
    semantic_scholar_enabled: bool = True
    openalex_enabled: bool = True
    dblp_enabled: bool = True
    semantic_scholar_api_key: str = ""
    openalex_mailto: str = ""


@dataclass
class ResearchFeishuConfig:
    """飞书数据源配置"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    poll_interval_minutes: int = 30


@dataclass
class ResearchConfig:
    enabled: bool = False
    database: ResearchDatabaseConfig = field(default_factory=ResearchDatabaseConfig)
    graph: ResearchGraphConfig = field(default_factory=ResearchGraphConfig)
    cache: ResearchCacheConfig = field(default_factory=ResearchCacheConfig)
    parsing: ResearchParsingConfig = field(default_factory=ResearchParsingConfig)
    arxiv: ResearchArxivConfig = field(default_factory=ResearchArxivConfig)
    embedding: ResearchEmbeddingConfig = field(default_factory=ResearchEmbeddingConfig)
    experiment: ResearchExperimentConfig = field(default_factory=ResearchExperimentConfig)
    search: ResearchSearchConfig = field(default_factory=ResearchSearchConfig)
    feishu: ResearchFeishuConfig = field(default_factory=ResearchFeishuConfig)


@dataclass
class WiringConfig:
    context: str = "default"
    memory: str = "default"
    toolsets: list[str] = field(
        default_factory=lambda: [
            "meta_common",
            "spawn",
            "schedule",
            "mcp",
            "research",
        ]
    )


@dataclass
class Config:
    provider: str
    model: str
    api_key: str
    system_prompt: str
    max_tokens: int = 8192
    max_iterations: int = 10
    memory_window: int = 40
    base_url: str | None = None
    extra_body: dict = field(default_factory=dict)
    channels: ChannelsConfig = field(default_factory=ChannelsConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    memory_optimizer_enabled: bool = True
    memory_optimizer_interval_seconds: int = 64800
    light_model: str = ""
    light_api_key: str = ""
    light_base_url: str = ""
    agent_model: str = ""
    agent_api_key: str = ""
    agent_base_url: str = ""
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    fitbit: FitbitIntegrationConfig = field(default_factory=FitbitIntegrationConfig)
    multimodal: bool = True
    vl_model: str = ""
    vl_api_key: str = ""
    vl_base_url: str = ""
    tool_search_enabled: bool = False
    spawn_enabled: bool = True
    dev_mode: bool = False
    peer_agents: list[PeerAgentConfig] = field(default_factory=list)
    wiring: WiringConfig = field(default_factory=WiringConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> Config:
        from importlib import import_module

        return import_module("agent.config").load_config(path)


__all__ = [
    "ChannelsConfig",
    "Config",
    "FitbitIntegrationConfig",
    "MemoryConfig",
    "MemoryEmbeddingConfig",
    "PeerAgentConfig",
    "QQChannelConfig",
    "QQBotChannelConfig",
    "QQBotGroupConfig",
    "QQGroupConfig",
    "ResearchConfig",
    "ResearchDatabaseConfig",
    "ResearchGraphConfig",
    "ResearchCacheConfig",
    "ResearchParsingConfig",
    "ResearchArxivConfig",
    "ResearchEmbeddingConfig",
    "ResearchExperimentConfig",
    "TelegramChannelConfig",
    "WiringConfig",
]
