"""
分布式爬虫管理器
支持动态反爬虫策略和增量数据更新
"""

import asyncio
import random
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..core.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CrawlTask:
    """爬虫任务定义"""
    url: str
    source_type: str
    parser_name: str
    priority: int = 1
    retry_count: int = 0
    max_retries: int = 3
    last_crawled: Optional[datetime] = None
    metadata: Dict[str, Any] = None


class AntiDetectionStrategy:
    """反爬虫检测策略"""
    
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]
        
        self.proxies = []  # 代理池，需要外部配置
        self.session_cookies = {}
    
    def get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(self.user_agents)
    
    def get_random_delay(self, base_delay: float = 1.0) -> float:
        """获取随机延迟时间"""
        return base_delay + random.uniform(0.5, 2.0)
    
    def get_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """生成请求头"""
        headers = {
            'User-Agent': self.get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        if referer:
            headers['Referer'] = referer
            
        return headers


class CrawlerManager:
    """分布式爬虫管理器"""
    
    def __init__(self):
        self.task_queue: List[CrawlTask] = []
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.anti_detection = AntiDetectionStrategy()
        self.max_workers = config.data_source.concurrent_requests
        self.base_delay = config.data_source.request_delay
        
        # 增量更新配置
        self.last_update_times: Dict[str, datetime] = {}
        
    async def add_task(self, task: CrawlTask):
        """添加爬虫任务"""
        # 检查是否需要增量更新
        if self.should_crawl(task):
            self.task_queue.append(task)
            logger.info(f"添加爬虫任务: {task.url} - {task.source_type}")
    
    def should_crawl(self, task: CrawlTask) -> bool:
        """判断是否需要爬取（增量更新逻辑）"""
        if not task.last_crawled:
            return True
        
        # 根据数据源类型设置更新间隔
        update_intervals = {
            'government_tender': timedelta(hours=1),
            'patent': timedelta(hours=24),
            'regulation': timedelta(hours=1),
            'supplier': timedelta(hours=6),
            'market_report': timedelta(hours=6)
        }
        
        interval = update_intervals.get(task.source_type, timedelta(hours=6))
        return datetime.now() - task.last_crawled > interval
    
    async def crawl_with_requests(self, task: CrawlTask) -> Optional[Dict[str, Any]]:
        """使用requests进行爬取"""
        try:
            headers = self.anti_detection.get_headers()
            
            async with aiohttp.ClientSession(headers=headers) as session:
                await asyncio.sleep(self.anti_detection.get_random_delay(self.base_delay))
                
                async with session.get(task.url, timeout=30) as response:
                    if response.status == 200:
                        content = await response.text()
                        return {
                            'url': task.url,
                            'content': content,
                            'status_code': response.status,
                            'headers': dict(response.headers),
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        logger.warning(f"HTTP {response.status} for {task.url}")
                        return None
                        
        except Exception as e:
            logger.error(f"爬取失败 {task.url}: {str(e)}")
            return None
    
    def crawl_with_selenium(self, task: CrawlTask) -> Optional[Dict[str, Any]]:
        """使用Selenium进行动态页面爬取"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument(f'--user-agent={self.anti_detection.get_random_user_agent()}')
            
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                driver.get(task.url)
                
                # 等待页面加载完成
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # 模拟人类行为
                time.sleep(random.uniform(2, 5))
                
                # 滚动页面以触发懒加载
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                content = driver.page_source
                
                return {
                    'url': task.url,
                    'content': content,
                    'status_code': 200,
                    'timestamp': datetime.now().isoformat()
                }
                
            finally:
                driver.quit()
                
        except Exception as e:
            logger.error(f"Selenium爬取失败 {task.url}: {str(e)}")
            return None
    
    async def process_task(self, task: CrawlTask) -> Optional[Dict[str, Any]]:
        """处理单个爬虫任务"""
        logger.info(f"开始处理任务: {task.url}")
        
        # 根据页面类型选择爬取方式
        if task.metadata and task.metadata.get('requires_js', False):
            # 需要JavaScript渲染的页面使用Selenium
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.crawl_with_selenium, task
            )
        else:
            # 静态页面使用aiohttp
            result = await self.crawl_with_requests(task)
        
        if result:
            task.last_crawled = datetime.now()
            task.retry_count = 0
            logger.info(f"任务完成: {task.url}")
        else:
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                # 重新加入队列
                await asyncio.sleep(60)  # 等待1分钟后重试
                await self.add_task(task)
                logger.info(f"任务重试 {task.retry_count}/{task.max_retries}: {task.url}")
        
        return result
    
    async def run_crawler(self):
        """运行爬虫管理器"""
        logger.info("启动分布式爬虫管理器")
        
        while True:
            if not self.task_queue:
                await asyncio.sleep(10)
                continue
            
            # 按优先级排序任务
            self.task_queue.sort(key=lambda x: x.priority, reverse=True)
            
            # 创建工作任务
            tasks = []
            for _ in range(min(self.max_workers, len(self.task_queue))):
                if self.task_queue:
                    task = self.task_queue.pop(0)
                    tasks.append(self.process_task(task))
            
            # 并发执行任务
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 处理结果
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"任务执行异常: {str(result)}")
                    elif result:
                        # 将结果发送到数据处理管道
                        await self.send_to_pipeline(result)
            
            await asyncio.sleep(1)
    
    async def send_to_pipeline(self, data: Dict[str, Any]):
        """将爬取结果发送到数据处理管道"""
        try:
            # 这里可以接入消息队列（如Redis、RabbitMQ）
            # 暂时使用日志记录
            logger.info(f"数据采集完成: {data['url']}, 大小: {len(data['content'])} 字符")
            
            # TODO: 实现实际的数据管道集成
            # await self.data_pipeline.process(data)
            
        except Exception as e:
            logger.error(f"数据管道处理失败: {str(e)}")
    
    def add_government_tender_tasks(self):
        """添加政府招标数据采集任务"""
        tender_urls = [
            "http://www.ccgp.gov.cn/cggg/dfgg/",  # 地方公告
            "http://www.ccgp.gov.cn/cggg/zygg/",  # 中央公告
        ]
        
        for url in tender_urls:
            task = CrawlTask(
                url=url,
                source_type='government_tender',
                parser_name='government_tender_parser',
                priority=3,
                metadata={'requires_js': False}
            )
            asyncio.create_task(self.add_task(task))
    
    def add_patent_tasks(self):
        """添加专利数据采集任务"""
        # 这里应该集成实际的专利API
        patent_keywords = ['储能电池', '锂离子电池', '钠离子电池', '固态电池']
        
        for keyword in patent_keywords:
            task = CrawlTask(
                url=f"https://patents.google.com/xhr/query?q={keyword}",
                source_type='patent',
                parser_name='patent_parser',
                priority=2,
                metadata={'keyword': keyword, 'requires_js': True}
            )
            asyncio.create_task(self.add_task(task))
    
    async def start(self):
        """启动爬虫管理器"""
        logger.info("初始化爬虫任务...")
        
        # 添加初始任务
        self.add_government_tender_tasks()
        self.add_patent_tasks()
        
        # 启动爬虫
        await self.run_crawler()


# 爬虫管理器实例
crawler_manager = CrawlerManager()