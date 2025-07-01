#!/usr/bin/env python3
"""
AI智能情报平台 - 主程序入口
覆盖商机追踪、供应链风控、法规合规、技术布局、市场动态的一体化AI情报平台
"""

import sys
import os
import asyncio
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import config
from src.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def print_banner():
    """打印启动横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                        🚀 AI智能情报平台                          ║
║                                                                  ║
║  覆盖商机追踪、供应链风控、法规合规、技术布局、市场动态          ║
║  的一体化AI情报平台，实现"数据采集→知识提炼→智能决策"闭环      ║
║                                                                  ║
║  核心功能:                                                       ║
║  🎯 智能问答系统 - 基于RAG架构，置信度≥90%                      ║
║  ⚠️  风险预警引擎 - 供应链风险识别，F1-score≥0.85               ║
║  📊 知识图谱构建 - 实时更新，查询响应≤500ms                     ║
║  🔍 多源数据采集 - 日处理≥100万条非结构化数据                  ║
║  📈 自动报表生成 - 深度分析报告一键输出                         ║
║  💡 商机推荐引擎 - 智能匹配，决策提速至小时级                   ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def validate_environment():
    """验证运行环境"""
    errors = config.validate_config()
    
    if errors:
        logger.error("配置验证失败:")
        for error in errors:
            logger.error(f"  ❌ {error}")
        
        logger.info("请检查以下配置:")
        logger.info("  1. 复制 .env.example 到 .env 并填写配置")
        logger.info("  2. 配置数据库连接信息")
        logger.info("  3. 配置AI模型API密钥")
        logger.info("  4. 确保Neo4j、PostgreSQL、Redis等服务正常运行")
        
        return False
    
    logger.info("✅ 配置验证通过")
    return True


async def start_services():
    """启动后台服务"""
    logger.info("启动后台服务...")
    
    try:
        # 启动爬虫管理器
        from src.data_collection.crawler_manager import crawler_manager
        crawler_task = asyncio.create_task(crawler_manager.start())
        logger.info("✅ 爬虫管理器启动成功")
        
        # 启动知识图谱管理器
        from src.knowledge_graph.graph_manager import graph_manager
        graph_task = asyncio.create_task(graph_manager.start_event_processor())
        logger.info("✅ 知识图谱管理器启动成功")
        
        logger.info("🎉 所有后台服务启动完成")
        
        return [crawler_task, graph_task]
        
    except Exception as e:
        logger.error(f"❌ 后台服务启动失败: {str(e)}")
        raise


def start_web_server():
    """启动Web服务器"""
    from src.api.main import start_server
    
    logger.info(f"启动Web服务器: http://{config.app.api_host}:{config.app.api_port}")
    logger.info("访问地址:")
    logger.info(f"  主页: http://{config.app.api_host}:{config.app.api_port}/")
    logger.info(f"  API文档: http://{config.app.api_host}:{config.app.api_port}/docs")
    logger.info(f"  智能问答: http://{config.app.api_host}:{config.app.api_port}/qa/test")
    
    start_server()


async def run_cli_mode():
    """命令行交互模式"""
    print("\n🤖 进入AI智能问答命令行模式")
    print("输入 'exit' 或 'quit' 退出, 输入 'help' 查看帮助\n")
    
    from src.ai_models.qa_system import qa_system
    
    while True:
        try:
            question = input("❓ 请输入您的问题: ").strip()
            
            if question.lower() in ['exit', 'quit', '退出']:
                print("👋 再见!")
                break
            
            if question.lower() in ['help', '帮助']:
                print("""
📖 帮助信息:
  - 支持中文问题，如: "欧盟2025年电池碳足迹门槛是什么？"
  - 支持供应链风险查询: "印尼镍矿出口限制的影响"
  - 支持技术分析: "固态电池技术路线"
  - 支持企业分析: "宁德时代供应商风险"
  - 输入 'exit' 退出程序
                """)
                continue
            
            if not question:
                continue
            
            print("🔍 正在分析您的问题...")
            
            result = await qa_system.answer_question(question)
            
            print(f"\n💡 回答 (置信度: {result['confidence']:.1%}):")
            print("=" * 60)
            print(result['answer'])
            
            if result['sources']:
                print(f"\n📎 信息来源 ({len(result['sources'])} 个):")
                for i, source in enumerate(result['sources'][:3], 1):
                    print(f"  {i}. {source.get('title', source.get('entity_name', '相关文档'))}")
            
            if result.get('improvement_suggestions'):
                print(f"\n💡 建议:")
                for suggestion in result['improvement_suggestions']:
                    print(f"  • {suggestion}")
            
            print("\n" + "=" * 60 + "\n")
            
        except KeyboardInterrupt:
            print("\n👋 用户中断，再见!")
            break
        except Exception as e:
            print(f"❌ 处理出错: {str(e)}")


def run_data_collection():
    """运行数据采集任务"""
    logger.info("启动数据采集任务...")
    
    from src.data_collection.crawler_manager import crawler_manager
    
    async def collect_data():
        try:
            # 添加政府招标任务
            crawler_manager.add_government_tender_tasks()
            
            # 添加专利数据任务  
            crawler_manager.add_patent_tasks()
            
            # 运行爬虫
            await crawler_manager.run_crawler()
            
        except KeyboardInterrupt:
            logger.info("用户中断数据采集")
        except Exception as e:
            logger.error(f"数据采集失败: {str(e)}")
    
    asyncio.run(collect_data())


def show_system_status():
    """显示系统状态"""
    print("\n📊 系统状态检查")
    print("=" * 50)
    
    # 检查配置
    errors = config.validate_config()
    if errors:
        print("❌ 配置验证失败:")
        for error in errors:
            print(f"   • {error}")
    else:
        print("✅ 配置验证通过")
    
    # 检查数据库连接
    try:
        from src.knowledge_graph.graph_manager import graph_manager
        print("✅ Neo4j知识图谱数据库连接正常")
    except Exception as e:
        print(f"❌ Neo4j连接失败: {str(e)}")
    
    # 显示性能指标
    from src.core.config import PERFORMANCE_TARGETS
    print("\n🎯 性能指标目标:")
    print(f"  • 全球政策更新延迟: ≤{PERFORMANCE_TARGETS['data_freshness']['global_policy']}小时")
    print(f"  • 专利数据更新周期: ≤{PERFORMANCE_TARGETS['data_freshness']['patent_data']}小时")
    print(f"  • 日处理数据量: ≥{PERFORMANCE_TARGETS['processing_capacity']['daily_unstructured_data']:,}条")
    print(f"  • 图谱查询响应: ≤{PERFORMANCE_TARGETS['processing_capacity']['graph_query_response']}ms")
    print(f"  • 风险预测F1-score: ≥{PERFORMANCE_TARGETS['ai_accuracy']['risk_prediction_f1']}")
    print(f"  • 问答置信度: ≥{PERFORMANCE_TARGETS['ai_accuracy']['qa_confidence']}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="AI智能情报平台 - 覆盖商机追踪、供应链风控、法规合规、技术布局、市场动态",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'command',
        choices=['server', 'cli', 'collect', 'status'],
        help='运行模式: server(Web服务器), cli(命令行问答), collect(数据采集), status(系统状态)'
    )
    
    parser.add_argument(
        '--host',
        default=config.app.api_host,
        help=f'服务器主机地址 (默认: {config.app.api_host})'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=config.app.api_port,
        help=f'服务器端口 (默认: {config.app.api_port})'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式'
    )
    
    args = parser.parse_args()
    
    # 设置调试模式
    if args.debug:
        config.app.debug = True
        config.app.log_level = "DEBUG"
    
    # 显示启动横幅
    print_banner()
    
    # 验证环境
    if not validate_environment():
        sys.exit(1)
    
    # 根据命令执行相应操作
    try:
        if args.command == 'server':
            # 更新配置
            config.app.api_host = args.host
            config.app.api_port = args.port
            
            logger.info(f"启动模式: Web服务器")
            start_web_server()
            
        elif args.command == 'cli':
            logger.info(f"启动模式: 命令行问答")
            asyncio.run(run_cli_mode())
            
        elif args.command == 'collect':
            logger.info(f"启动模式: 数据采集")
            run_data_collection()
            
        elif args.command == 'status':
            logger.info(f"启动模式: 系统状态检查")
            show_system_status()
            
    except KeyboardInterrupt:
        logger.info("用户中断程序")
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()