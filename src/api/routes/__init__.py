"""
API路由模块
"""

from .qa import router as qa_router
from .dashboard import router as dashboard_router
from .admin import router as admin_router

__all__ = [
    'qa_router',
    'dashboard_router',
    'admin_router'
]