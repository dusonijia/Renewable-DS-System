"""
安全管理工具
提供数据加密、身份验证等安全功能
"""

import hashlib
import hmac
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

from ..core.config import config
from .logger import get_logger

logger = get_logger(__name__)


class SecurityManager:
    """安全管理器"""
    
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret_key = config.app.jwt_secret_key
        self.encryption_key = config.app.encryption_key
        
        # 初始化加密器
        try:
            if len(self.encryption_key) == 32:  # 如果是32字节的密钥
                from base64 import urlsafe_b64encode
                key = urlsafe_b64encode(self.encryption_key.encode()[:32])
                self.cipher = Fernet(key)
            else:
                # 生成新的密钥
                key = Fernet.generate_key()
                self.cipher = Fernet(key)
        except Exception as e:
            logger.warning(f"加密器初始化失败: {e}")
            self.cipher = None
    
    def hash_password(self, password: str) -> str:
        """密码哈希"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=config.app.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        
        try:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm="HS256")
            return encoded_jwt
        except Exception as e:
            logger.error(f"创建访问令牌失败: {e}")
            raise
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证访问令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("令牌已过期")
            return None
        except jwt.JWTError as e:
            logger.warning(f"令牌验证失败: {e}")
            return None
    
    def encrypt_data(self, data: str) -> Optional[str]:
        """加密数据"""
        if not self.cipher:
            logger.warning("加密器未初始化")
            return None
        
        try:
            encrypted_data = self.cipher.encrypt(data.encode())
            return encrypted_data.decode()
        except Exception as e:
            logger.error(f"数据加密失败: {e}")
            return None
    
    def decrypt_data(self, encrypted_data: str) -> Optional[str]:
        """解密数据"""
        if not self.cipher:
            logger.warning("加密器未初始化")
            return None
        
        try:
            decrypted_data = self.cipher.decrypt(encrypted_data.encode())
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"数据解密失败: {e}")
            return None
    
    def generate_secure_token(self, length: int = 32) -> str:
        """生成安全令牌"""
        return secrets.token_urlsafe(length)
    
    def generate_api_key(self) -> str:
        """生成API密钥"""
        return secrets.token_hex(32)
    
    def validate_api_key(self, api_key: str, stored_hash: str) -> bool:
        """验证API密钥"""
        # 使用HMAC进行安全比较
        computed_hash = hmac.new(
            self.secret_key.encode(),
            api_key.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_hash, stored_hash)
    
    def sanitize_input(self, input_data: str) -> str:
        """输入数据清理"""
        # 基础的输入清理
        if not isinstance(input_data, str):
            return str(input_data)
        
        # 移除潜在的恶意字符
        dangerous_chars = ['<', '>', '"', "'", '&', 'script', 'javascript:']
        cleaned_data = input_data
        
        for char in dangerous_chars:
            cleaned_data = cleaned_data.replace(char, '')
        
        return cleaned_data.strip()
    
    def check_rate_limit(self, identifier: str, max_requests: int = 100, window_minutes: int = 60) -> bool:
        """检查速率限制"""
        # TODO: 实现基于Redis的速率限制
        # 这里是简化实现
        return True
    
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """记录安全事件"""
        from .logger import audit_logger
        
        audit_logger.log_security_event(
            event_type=event_type,
            severity="medium",
            description=f"安全事件: {event_type}",
            **details
        )


# 全局安全管理器实例
security_manager = SecurityManager()