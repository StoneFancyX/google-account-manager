"""加密解密工具模块

- 密码哈希使用 bcrypt (主密码登录)
- 数据字段不再加密, 明文存储
"""
import bcrypt as _bcrypt


class CryptoManager:
    """数据加密管理器 (已禁用加密, 仅保留接口兼容)"""

    def __init__(self, master_password: str = "", **kwargs):
        pass

    def encrypt(self, data: str) -> str:
        return data or ""

    def decrypt(self, encrypted_data: str) -> str:
        return encrypted_data or ""

    @staticmethod
    def hash_password(password: str) -> str:
        """使用 bcrypt 哈希密码"""
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """验证 bcrypt 哈希"""
        return _bcrypt.checkpw(password.encode(), hashed.encode())
