"""数据库引擎与会话管理"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def ensure_schema_updates() -> None:
    """轻量 schema 兼容: 确保新增字段存在"""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("accounts"):
            return

        columns = {col["name"] for col in inspector.get_columns("accounts")}
        if "oauth_credential_json" in columns:
            return

        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN oauth_credential_json TEXT DEFAULT ''"))
        logger.info("[schema] 已补齐 accounts.oauth_credential_json")
    except Exception as e:
        logger.warning(f"[schema] schema 更新检查失败: {e}")


def get_db() -> Session:
    """FastAPI 依赖项：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
