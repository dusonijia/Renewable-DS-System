#!/usr/bin/env python3
"""
AI智能情报平台 - 快速启动脚本
用于开发和测试环境的快速启动
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

try:
    from src.api.main import app
    import uvicorn
    
    if __name__ == "__main__":
        print("""
╔══════════════════════════════════════════════════════════════════╗
║                    🚀 AI智能情报平台 - 快速启动                     ║
║                                                                  ║
║  开发测试环境启动中...                                             ║
║                                                                  ║
║  访问地址:                                                        ║
║  • 主页: http://localhost:8000                                   ║
║  • API文档: http://localhost:8000/docs                           ║
║  • 智能问答: http://localhost:8000/qa/test                       ║
║  • 监控面板: http://localhost:8000/dashboard                     ║
║  • 管理面板: http://localhost:8000/admin                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        
        uvicorn.run(
            app,
            host="0.0.0.0", 
            port=8000, 
            reload=True,
            log_level="info"
        )

except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保已安装所需依赖:")
    print("pip install fastapi uvicorn pydantic")
    sys.exit(1)
except Exception as e:
    print(f"❌ 启动失败: {e}")
    sys.exit(1)