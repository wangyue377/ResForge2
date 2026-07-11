"""
Neo4j 图数据库连接管理
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession as Neo4jSession

from agent.config_models import ResearchGraphConfig

logger = logging.getLogger(__name__)


class ResearchGraph:
    """Neo4j 异步图数据库连接管理器"""

    def __init__(self, config: ResearchGraphConfig):
        self.config = config
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
            max_connection_pool_size=10,
            connection_acquisition_timeout=30,
        )
        logger.info("ResearchGraph initialized: %s", config.uri)

    async def verify_connectivity(self) -> bool:
        """验证图数据库连接"""
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception as e:
            err_str = str(e).lower()
            if "auth" in err_str or "unauthorized" in err_str or "authentication" in err_str:
                logger.error(
                    "Neo4j 认证失败。请执行以下命令重置凭据：\n"
                    "  1. docker compose -f docker/docker-compose.research.yml down\n"
                    "  2. docker volume rm resforge_neo4jdata\n"
                    "  3. docker compose -f docker/docker-compose.research.yml up -d\n"
                    "或者检查 config.toml 中的 [research.graph] user/password 是否与 docker-compose 一致。"
                )
            elif "connection refused" in err_str or "connect" in err_str:
                logger.error(
                    "Neo4j 连接被拒。请先启动容器：\n"
                    "  docker compose -f docker/docker-compose.research.yml up -d"
                )
            else:
                logger.error("Neo4j 连接失败: %s", e)
            return False

    async def run_query(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """执行 Cypher 查询并返回结果列表"""
        async with self.driver.session() as session:
            result = await session.run(cypher, params or {})
            return await result.data()

    async def run_query_in_tx(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """在事务中执行 Cypher 查询"""
        async with self.driver.session() as session:
            async with session.begin_transaction() as tx:
                result = await tx.run(cypher, params or {})
                return await result.data()

    async def close(self):
        await self.driver.close()
        logger.info("Neo4j connection closed")
