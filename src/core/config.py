"""
系统配置管理模块
"""
import os
from typing import Optional, List
from pydantic import BaseSettings, Field
from dotenv import load_dotenv

load_dotenv()


class DatabaseConfig(BaseSettings):
    """数据库配置"""
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_db: str = Field(default="ai_intelligence_platform", env="POSTGRES_DB")
    postgres_user: str = Field(default="admin", env="POSTGRES_USER")
    postgres_password: str = Field(default="password", env="POSTGRES_PASSWORD")
    
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    neo4j_uri: str = Field(default="bolt://localhost:7687", env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", env="NEO4J_USER")
    neo4j_password: str = Field(default="password", env="NEO4J_PASSWORD")
    
    elasticsearch_host: str = Field(default="localhost", env="ELASTICSEARCH_HOST")
    elasticsearch_port: int = Field(default=9200, env="ELASTICSEARCH_PORT")
    elasticsearch_index: str = Field(default="intelligence_data", env="ELASTICSEARCH_INDEX")
    
    @property
    def postgres_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"
    
    @property
    def elasticsearch_url(self) -> str:
        return f"http://{self.elasticsearch_host}:{self.elasticsearch_port}"


class AIModelConfig(BaseSettings):
    """AI模型配置"""
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")
    azure_openai_endpoint: Optional[str] = Field(default=None, env="AZURE_OPENAI_ENDPOINT")
    azure_openai_key: Optional[str] = Field(default=None, env="AZURE_OPENAI_KEY")
    
    # 模型选择
    embedding_model: str = Field(default="text-embedding-ada-002")
    chat_model: str = Field(default="gpt-3.5-turbo")
    
    # 本地模型路径
    local_model_path: str = Field(default="./data/models")
    
    # NLP模型配置
    bert_model_name: str = Field(default="bert-base-chinese")
    sentence_transformer_model: str = Field(default="all-MiniLM-L6-v2")


class DataSourceConfig(BaseSettings):
    """数据源配置"""
    # 专利数据源
    derwent_api_key: Optional[str] = Field(default=None, env="DERWENT_API_KEY")
    zhihuiya_api_key: Optional[str] = Field(default=None, env="ZHIHUIYA_API_KEY")
    
    # 市场数据源
    bloomberg_api_key: Optional[str] = Field(default=None, env="BLOOMBERG_API_KEY")
    
    # 爬虫配置
    user_agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", env="USER_AGENT")
    request_delay: float = Field(default=1.0, env="REQUEST_DELAY")
    concurrent_requests: int = Field(default=16, env="CONCURRENT_REQUESTS")
    
    # 数据更新频率（小时）
    policy_update_interval: int = Field(default=1)
    patent_update_interval: int = Field(default=24)
    market_update_interval: int = Field(default=6)


class AppConfig(BaseSettings):
    """应用配置"""
    app_name: str = Field(default="AI Intelligence Platform", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    secret_key: str = Field(default="your-secret-key", env="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # 日志配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", env="LOG_FILE")
    
    # API配置
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    
    # 安全配置
    encryption_key: str = Field(default="your-encryption-key", env="ENCRYPTION_KEY")
    jwt_secret_key: str = Field(default="your-jwt-secret", env="JWT_SECRET_KEY")
    
    # 监控配置
    prometheus_port: int = Field(default=8000, env="PROMETHEUS_PORT")
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")


class SystemConfig:
    """系统配置管理器"""
    
    def __init__(self):
        self.database = DatabaseConfig()
        self.ai_model = AIModelConfig()
        self.data_source = DataSourceConfig()
        self.app = AppConfig()
    
    def validate_config(self) -> List[str]:
        """验证配置的完整性"""
        errors = []
        
        # 检查必要的API密钥
        if not self.ai_model.openai_api_key and not self.ai_model.azure_openai_key:
            errors.append("需要配置OpenAI或Azure OpenAI的API密钥")
        
        # 检查数据库连接
        if not all([
            self.database.postgres_host,
            self.database.postgres_user,
            self.database.postgres_password
        ]):
            errors.append("PostgreSQL数据库配置不完整")
        
        # 检查知识图谱数据库
        if not all([
            self.database.neo4j_uri,
            self.database.neo4j_user,
            self.database.neo4j_password
        ]):
            errors.append("Neo4j知识图谱数据库配置不完整")
        
        return errors


# 全局配置实例
config = SystemConfig()


# 性能指标配置
PERFORMANCE_TARGETS = {
    "data_freshness": {
        "global_policy": 1,  # 小时
        "patent_data": 24,   # 小时
        "supplier_risk": 6,  # 小时
    },
    "processing_capacity": {
        "daily_unstructured_data": 1000000,  # 条/日
        "graph_query_response": 500,         # 毫秒
    },
    "ai_accuracy": {
        "risk_prediction_f1": 0.85,
        "qa_confidence": 0.90,
        "supplier_risk_identification": 0.60,  # 提升比例
    }
}


# 数据源映射
DATA_SOURCES = {
    "government_tenders": [
        "http://www.ccgp.gov.cn/",  # 中国政府采购网
        "https://www.ggzy.gov.cn/", # 全国公共资源交易平台
    ],
    "industry_exhibitions": [
        "https://www.snec.org.cn/",  # 光伏展会
        "https://www.ces.tech/",     # 储能展会
    ],
    "patent_databases": [
        "derwent_innovation",
        "zhihuiya",
        "google_patents"
    ],
    "market_research": [
        "bloomberg_new_energy",
        "ihs_markit",
        "wood_mackenzie"
    ],
    "regulatory_sources": [
        "china_miit",      # 工信部
        "eu_commission",   # 欧盟委员会
        "us_doe"          # 美国能源部
    ]
}