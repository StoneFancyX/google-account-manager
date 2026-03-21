"""数据库引擎与会话管理"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def ensure_schema_updates() -> None:
    """轻量 schema 兼容: 确保新增字段/表存在"""
    from models.orm import Base
    # 自动创建新表 (不影响已有表)
    Base.metadata.create_all(bind=engine)

    try:
        inspector = inspect(engine)
        if not inspector.has_table("accounts"):
            return

        columns = {col["name"] for col in inspector.get_columns("accounts")}

        new_columns = {
            "oauth_credential_json": "TEXT DEFAULT ''",
            "country": "VARCHAR DEFAULT ''",
            "country_cn": "VARCHAR DEFAULT ''",
        }

        with engine.begin() as conn:
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    conn.execute(text(f"ALTER TABLE accounts ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"[schema] 已补齐 accounts.{col_name}")
    except Exception as e:
        logger.warning(f"[schema] schema 更新检查失败: {e}")


def get_db() -> Session:
    """FastAPI 依赖项：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
