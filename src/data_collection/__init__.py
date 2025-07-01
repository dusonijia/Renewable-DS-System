"""
数据采集模块
实现多源情报采集与结构化处理
"""

from .crawler_manager import CrawlerManager
from .data_parser import DataParser
from .suppliers import SupplierDataCollector
from .patents import PatentDataCollector
from .regulations import RegulationCollector
from .market_data import MarketDataCollector

__all__ = [
    'CrawlerManager',
    'DataParser',
    'SupplierDataCollector',
    'PatentDataCollector',
    'RegulationCollector',
    'MarketDataCollector'
]