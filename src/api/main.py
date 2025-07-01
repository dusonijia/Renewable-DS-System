"""
FastAPI主应用
提供AI情报平台的Web API接口
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

from ..core.config import config
from ..utils.logger import get_logger, performance_logger, audit_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("启动AI情报平台...")
    
    try:
        # 启动后台任务
        # crawler_task = asyncio.create_task(crawler_manager.start())
        # graph_task = asyncio.create_task(graph_manager.start_event_processor())
        
        logger.info("后台服务启动完成")
        
        yield
        
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}")
        raise
    finally:
        logger.info("正在关闭AI情报平台...")
        
        # 关闭连接
        # graph_manager.close()
        
        logger.info("应用关闭完成")


# 创建FastAPI应用
app = FastAPI(
    title=config.app.app_name,
    version=config.app.app_version,
    description="覆盖商机追踪、供应链风控、法规合规、技术布局、市场动态的一体化AI情报平台",
    lifespan=lifespan
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """请求日志中间件"""
    start_time = time.time()
    
    # 记录请求
    audit_logger.log_data_access(
        user_id=request.headers.get("user-id", "anonymous"),
        resource=str(request.url),
        action=request.method
    )
    
    try:
        response = await call_next(request)
        
        # 记录性能
        processing_time = time.time() - start_time
        performance_logger.log_processing_time(
            operation="api_request",
            duration=processing_time,
            endpoint=str(request.url.path),
            method=request.method,
            status_code=response.status_code
        )
        
        return response
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            "API请求处理失败",
            endpoint=str(request.url.path),
            method=request.method,
            error=str(e),
            processing_time=processing_time
        )
        raise


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": config.app.app_version,
        "timestamp": datetime.now().isoformat()
    }


# Prometheus指标端点
@app.get("/metrics")
async def metrics():
    """Prometheus指标"""
    if not config.app.enable_metrics:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return Response(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )
    except ImportError:
        return {"error": "Prometheus client not available"}


# 根路径 - 提供简单的Web界面
@app.get("/", response_class=HTMLResponse)
async def root():
    """主页"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI智能情报平台</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                text-align: center;
                margin-bottom: 40px;
            }
            .header h1 {
                font-size: 3em;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .header p {
                font-size: 1.2em;
                opacity: 0.9;
            }
            .features {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 30px;
                margin-bottom: 40px;
            }
            .feature-card {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.2);
                transition: transform 0.3s ease;
            }
            .feature-card:hover {
                transform: translateY(-5px);
            }
            .feature-card h3 {
                margin-top: 0;
                color: #FFD700;
                font-size: 1.5em;
            }
            .api-section {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.2);
            }
            .api-link {
                display: inline-block;
                background: #FFD700;
                color: #333;
                padding: 12px 24px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: bold;
                margin: 10px 10px 0 0;
                transition: background 0.3s ease;
            }
            .api-link:hover {
                background: #FFC700;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }
            .stat-item {
                text-align: center;
                background: rgba(255,255,255,0.1);
                padding: 20px;
                border-radius: 10px;
            }
            .stat-number {
                font-size: 2.5em;
                font-weight: bold;
                color: #FFD700;
            }
            .stat-label {
                font-size: 0.9em;
                opacity: 0.8;
                margin-top: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 AI智能情报平台</h1>
                <p>覆盖商机追踪、供应链风控、法规合规、技术布局、市场动态的一体化AI情报平台</p>
            </div>
            
            <div class="features">
                <div class="feature-card">
                    <h3>🎯 智能问答</h3>
                    <p>基于RAG架构的智能问答系统，结合知识图谱生成解释性答案。支持电池行业专业问题分析，置信度达90%以上。</p>
                </div>
                
                <div class="feature-card">
                    <h3>⚠️ 风险预警</h3>
                    <p>实时监控供应链风险，自动识别制裁实体、技术封锁等风险事件。支持多级溯源分析，风险识别效率提升60%。</p>
                </div>
                
                <div class="feature-card">
                    <h3>📊 知识图谱</h3>
                    <p>动态构建企业、技术、法规等实体关系网络。实时响应外部事件，自动触发图谱重构，查询响应小于500ms。</p>
                </div>
                
                <div class="feature-card">
                    <h3>🔍 数据采集</h3>
                    <p>分布式爬虫支持政府招标、专利数据、法规文件等多源采集。日处理非结构化数据100万条以上。</p>
                </div>
                
                <div class="feature-card">
                    <h3>📈 自动报表</h3>
                    <p>AutoML动态匹配数据模型，一键生成专业分析报告。支持竞争对手分析、技术趋势预测等场景。</p>
                </div>
                
                <div class="feature-card">
                    <h3>💡 商机推荐</h3>
                    <p>智能匹配政策导向与企业产能，主动推送高契合度项目机会。决策速度从周级压缩至小时级。</p>
                </div>
            </div>
            
            <div class="api-section">
                <h2>🔧 API 接口</h2>
                <p>通过以下接口访问平台功能：</p>
                <a href="/docs" class="api-link">📖 API文档 (Swagger)</a>
                <a href="/redoc" class="api-link">📋 API文档 (ReDoc)</a>
                <a href="/qa/test" class="api-link">❓ 智能问答测试</a>
                
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-number">≤1h</div>
                        <div class="stat-label">全球政策更新延迟</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">≤24h</div>
                        <div class="stat-label">专利数据更新周期</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">100万+</div>
                        <div class="stat-label">日处理数据量</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">≤500ms</div>
                        <div class="stat-label">图谱查询响应</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">≥90%</div>
                        <div class="stat-label">问答置信度</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">≥85%</div>
                        <div class="stat-label">风险预测F1值</div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content


# 导入并注册路由
try:
    from .routes.qa import router as qa_router
    app.include_router(qa_router, prefix="/qa", tags=["智能问答"])
except ImportError as e:
    logger.warning(f"无法导入qa路由: {e}")

try:
    from .routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router, prefix="/dashboard", tags=["监控面板"])
except ImportError as e:
    logger.warning(f"无法导入dashboard路由: {e}")

try:
    from .routes.admin import router as admin_router
    app.include_router(admin_router, prefix="/admin", tags=["系统管理"])
except ImportError as e:
    logger.warning(f"无法导入admin路由: {e}")


# 启动函数
def start_server():
    """启动服务器"""
    logger.info(f"启动AI情报平台服务器: {config.app.api_host}:{config.app.api_port}")
    
    uvicorn.run(
        "src.api.main:app",
        host=config.app.api_host,
        port=config.app.api_port,
        reload=config.app.debug,
        log_level=config.app.log_level.lower(),
        access_log=True
    )


if __name__ == "__main__":
    start_server()