"""
日志管理模块
支持结构化日志记录和监控
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import structlog
import json
from datetime import datetime

from ..core.config import config


def setup_logging() -> None:
    """设置日志配置"""
    
    # 确保日志目录存在
    log_dir = Path(config.app.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 配置标准logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.app.log_level.upper()),
    )
    
    # 添加文件处理器
    file_handler = logging.FileHandler(config.app.log_file, encoding='utf-8')
    file_handler.setLevel(getattr(logging, config.app.log_level.upper()))
    
    # JSON格式化器
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            
            # 添加异常信息
            if record.exc_info:
                log_data['exception'] = self.formatException(record.exc_info)
            
            # 添加额外的上下文信息
            if hasattr(record, 'extra_data'):
                log_data.update(record.extra_data)
            
            return json.dumps(log_data, ensure_ascii=False)
    
    file_handler.setFormatter(JSONFormatter())
    
    # 获取根日志器并添加处理器
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> structlog.BoundLogger:
    """获取结构化日志器"""
    return structlog.get_logger(name)


class LoggerAdapter:
    """日志适配器，提供额外的上下文信息"""
    
    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger
        self.context: Dict[str, Any] = {}
    
    def bind(self, **kwargs) -> 'LoggerAdapter':
        """绑定上下文信息"""
        new_adapter = LoggerAdapter(self.logger)
        new_adapter.context = {**self.context, **kwargs}
        return new_adapter
    
    def _log(self, level: str, message: str, **kwargs):
        """内部日志方法"""
        log_data = {**self.context, **kwargs}
        getattr(self.logger, level)(message, **log_data)
    
    def debug(self, message: str, **kwargs):
        self._log('debug', message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log('info', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log('warning', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log('error', message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log('critical', message, **kwargs)


class PerformanceLogger:
    """性能日志记录器"""
    
    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger
    
    def log_processing_time(self, operation: str, duration: float, **context):
        """记录处理时间"""
        self.logger.info(
            "Performance metric",
            operation=operation,
            duration_seconds=duration,
            **context
        )
    
    def log_throughput(self, operation: str, count: int, duration: float, **context):
        """记录吞吐量"""
        throughput = count / duration if duration > 0 else 0
        self.logger.info(
            "Throughput metric",
            operation=operation,
            count=count,
            duration_seconds=duration,
            throughput_per_second=throughput,
            **context
        )
    
    def log_resource_usage(self, operation: str, memory_mb: float, cpu_percent: float, **context):
        """记录资源使用情况"""
        self.logger.info(
            "Resource usage",
            operation=operation,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            **context
        )


class ErrorTracker:
    """错误跟踪器"""
    
    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger
        self.error_counts: Dict[str, int] = {}
    
    def track_error(self, error_type: str, error_message: str, **context):
        """跟踪错误"""
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        self.logger.error(
            "Error tracked",
            error_type=error_type,
            error_message=error_message,
            error_count=self.error_counts[error_type],
            **context
        )
    
    def get_error_summary(self) -> Dict[str, int]:
        """获取错误统计"""
        return self.error_counts.copy()


class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger
    
    def log_data_access(self, user_id: str, resource: str, action: str, **context):
        """记录数据访问"""
        self.logger.info(
            "Data access",
            user_id=user_id,
            resource=resource,
            action=action,
            timestamp=datetime.now().isoformat(),
            **context
        )
    
    def log_system_change(self, user_id: str, change_type: str, description: str, **context):
        """记录系统变更"""
        self.logger.info(
            "System change",
            user_id=user_id,
            change_type=change_type,
            description=description,
            timestamp=datetime.now().isoformat(),
            **context
        )
    
    def log_security_event(self, event_type: str, severity: str, description: str, **context):
        """记录安全事件"""
        self.logger.warning(
            "Security event",
            event_type=event_type,
            severity=severity,
            description=description,
            timestamp=datetime.now().isoformat(),
            **context
        )


# 初始化日志系统
setup_logging()

# 创建默认日志器实例
default_logger = get_logger("ai_intelligence_platform")
performance_logger = PerformanceLogger(default_logger)
error_tracker = ErrorTracker(default_logger)
audit_logger = AuditLogger(default_logger)