"""依赖注入 - 集中管理 FastAPI 依赖项"""
from datetime import datetime, timezone, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from sqlalchemy.orm import Session

import config
from models.database import get_db
from utils.crypto import CryptoManager
from services.auth import AuthService
from services.account import AccountService
from services.group import GroupService

security = HTTPBearer()


class AppState:
    """应用运行时状态"""

    def __init__(self):
        self.crypto: CryptoManager = CryptoManager()
        self.logged_in: bool = False


# 由 router 登录时设置
state: AppState = AppState()


# ---- Service 依赖（每次请求独立 Session）----

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_account_service(db: Session = Depends(get_db)) -> AccountService:
    return AccountService(db)


def get_group_service(
    db: Session = Depends(get_db),
    account_service: AccountService = Depends(get_account_service),
) -> GroupService:
    return GroupService(db, account_service)


# ---- 认证依赖 ----

def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """校验 JWT Token"""
    try:
        payload = jwt.decode(
            credentials.credentials,
            config.SECRET_KEY,
            algorithms=[config.ALGORITHM],
        )
        if not state.logged_in:
            raise HTTPException(status_code=401, detail="会话已过期，请重新登录")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="无效的 Token")


# ---- Token 工具 ----

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)


def verify_ws_token(token: str) -> bool:
    """校验 WebSocket 连接的 Token (query param)"""
    try:
        jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        return state.logged_in
    except Exception:
        return False
