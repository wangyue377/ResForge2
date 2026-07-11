"""
PostgreSQL 异步数据库连接管理

使用 SQLAlchemy async 模式 + asyncpg 驱动。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agent.config_models import ResearchDatabaseConfig
from research.models.paper import Base

logger = logging.getLogger(__name__)


class ResearchDatabase:
    """PostgreSQL + pgvector 异步连接池管理器"""

    def __init__(self, config: ResearchDatabaseConfig):
        self.config = config
        dsn = (
            f"postgresql+asyncpg://{config.user}:{config.password}"
            f"@{config.host}:{config.port}/{config.db}"
        )
        self.engine = create_async_engine(
            dsn,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            echo=False,
        )
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info(
            "ResearchDatabase initialized: %s@%s:%s/%s",
            config.user, config.host, config.port, config.db,
        )

    async def init_tables(self):
        """创建所有表（开发用；生产建议用 Alembic 迁移）"""
        async with self.engine.begin() as conn:
            # 先创建 pgvector 扩展
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created / verified")

    async def ensure_vector_columns(self):
        """确保论文和分块的向量列存在"""
        async with self.engine.begin() as conn:
            # 给 papers 表添加 vector 列（如果不存在）
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='papers' AND column_name='embedding'
                    ) THEN
                        ALTER TABLE papers ADD COLUMN embedding vector(1024);
                        CREATE INDEX IF NOT EXISTS idx_papers_embedding
                            ON papers USING hnsw (embedding vector_cosine_ops);
                    END IF;
                END $$;
            """))
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='paper_chunks' AND column_name='embedding'
                    ) THEN
                        ALTER TABLE paper_chunks ADD COLUMN embedding vector(1024);
                        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
                            ON paper_chunks USING hnsw (embedding vector_cosine_ops);
                    END IF;
                END $$;
            """))
        logger.info("Vector columns verified")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取异步数据库会话（上下文管理器形式）"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def verify_connectivity(self) -> bool:
        """验证数据库连接"""
        try:
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error("Database connectivity check failed: %s", e)
            return False

    async def close(self):
        await self.engine.dispose()
        logger.info("Database connection closed")
