"""认证服务 - 处理密码设置、验证"""
from sqlalchemy.orm import Session
from models.orm import Config
from utils.crypto import CryptoManager


class AuthService:
    """认证业务逻辑"""

    def __init__(self, db: Session):
        self.db = db

    def has_master_password(self) -> bool:
        row = self.db.query(Config).filter_by(key="master_password_hash").first()
        return row is not None

    def set_master_password(self, password: str):
        """设置主密码（首次使用），使用 bcrypt 哈希"""
        password_hash = CryptoManager.hash_password(password)
        row = self.db.query(Config).filter_by(key="master_password_hash").first()
        if row:
            row.value = password_hash
        else:
            self.db.add(Config(key="master_password_hash", value=password_hash))
        self.db.commit()

    def verify_master_password(self, password: str) -> bool:
        """验证主密码，兼容旧版 SHA-256 并自动迁移到 bcrypt"""
        row = self.db.query(Config).filter_by(key="master_password_hash").first()
        if row is None:
            return False

        stored_hash = row.value

        # 旧版 SHA-256 哈希兼容（64 位十六进制字符串）
        if len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash):
            import hashlib
            if stored_hash == hashlib.sha256(password.encode()).hexdigest():
                # 验证通过，自动迁移到 bcrypt
                self.set_master_password(password)
                return True
            return False

        return CryptoManager.verify_password(password, stored_hash)
