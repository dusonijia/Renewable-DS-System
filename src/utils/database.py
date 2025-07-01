"""
数据库管理工具
"""

from typing import Optional
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from ..core.config import config
from .logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.engine = None
        self.async_engine = None
        self.session_factory = None
        
    def init_database(self):
        """初始化数据库连接"""
        try:
            # 同步引擎
            self.engine = create_engine(config.database.postgres_url)
            
            # 异步引擎
            async_url = config.database.postgres_url.replace('postgresql://', 'postgresql+asyncpg://')
            self.async_engine = create_async_engine(async_url)
            
            # 会话工厂
            self.session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False
            )
            
            logger.info("数据库连接初始化成功")
            
        except Exception as e:
            logger.error(f"数据库连接初始化失败: {str(e)}")
            raise
    
    def get_session(self):
        """获取数据库会话"""
        if not self.session_factory:
            self.init_database()
        return self.session_factory()
    
    async def get_async_session(self) -> AsyncSession:
        """获取异步数据库会话"""
        if not self.async_engine:
            self.init_database()
        return AsyncSession(self.async_engine)
    
    def close(self):
        """关闭数据库连接"""
        if self.engine:
            self.engine.dispose()
        if self.async_engine:
            self.async_engine.dispose()


# 全局数据库管理器实例
db_manager = DatabaseManager()