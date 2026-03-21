"""系统设置路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from deps import verify_token
from models.database import get_db
from models.orm import Config


router = APIRouter(
    prefix="/settings",
    tags=["系统设置"],
    dependencies=[Depends(verify_token)],
)

# ---- 默认值 ----

DEFAULTS = {
    "debug_mode": "false",
    "headless_mode": "false",
    "default_sms_provider_id": "",
}


# ---- 工具函数 ----

def _get(db: Session, key: str) -> str:
    """获取设置值, 不存在则返回默认值"""
    row = db.query(Config).filter(Config.key == key).first()
    if row:
        return row.value
    return DEFAULTS.get(key, "")


def _set(db: Session, key: str, value: str):
    """写入设置值"""
    row = db.query(Config).filter(Config.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Config(key=key, value=value))
    db.commit()


def get_debug_mode(db: Session) -> bool:
    """获取调试模式状态 (供其他模块调用)"""
    return _get(db, "debug_mode") == "true"


# ---- 请求/响应模型 ----

class SettingsResponse(BaseModel):
    debug_mode: bool
    headless_mode: bool
    default_sms_provider_id: str


class SettingsUpdateRequest(BaseModel):
    debug_mode: Optional[bool] = None
    headless_mode: Optional[bool] = None
    default_sms_provider_id: Optional[str] = None


# ---- 路由 ----

@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """获取所有系统设置"""
    return SettingsResponse(
        debug_mode=_get(db, "debug_mode") == "true",
        headless_mode=_get(db, "headless_mode") == "true",
        default_sms_provider_id=_get(db, "default_sms_provider_id"),
    )


@router.put("")
def update_settings(req: SettingsUpdateRequest, db: Session = Depends(get_db)):
    """更新系统设置"""
    if req.debug_mode is not None:
        _set(db, "debug_mode", "true" if req.debug_mode else "false")
    if req.headless_mode is not None:
        _set(db, "headless_mode", "true" if req.headless_mode else "false")
    if req.default_sms_provider_id is not None:
        _set(db, "default_sms_provider_id", req.default_sms_provider_id)

    # 返回更新后的完整设置
    return SettingsResponse(
        debug_mode=_get(db, "debug_mode") == "true",
        headless_mode=_get(db, "headless_mode") == "true",
        default_sms_provider_id=_get(db, "default_sms_provider_id"),
    )
