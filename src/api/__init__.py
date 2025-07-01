"""
API模块
提供REST API接口和Web界面
"""

from .main import app
from .routes import qa_router, dashboard_router, admin_router

__all__ = [
    'app',
    'qa_router',
    'dashboard_router', 
    'admin_router'
]