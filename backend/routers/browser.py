"""浏览器配置路由 - Profile CRUD + 启动/停止"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from deps import verify_token
from models.database import get_db
from models.orm import BrowserProfile, Account
from models.schemas import BrowserProfileCreate, BrowserProfileUpdate
from services.browser import browser_manager

router = APIRouter(
    prefix="/browser-profiles",
    tags=["浏览器配置"],
    dependencies=[Depends(verify_token)],
)


def _to_dict(p: BrowserProfile, running_ids: list) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "account_id": p.account_id,
        "account_email": p.account.email if p.account else "",
        "proxy_type": p.proxy_type or "",
        "proxy_host": p.proxy_host or "",
        "proxy_port": p.proxy_port,
        "proxy_username": p.proxy_username or "",
        "proxy_password": p.proxy_password or "",
        "user_agent": p.user_agent or "",
        "os_type": p.os_type or "macos",
        "timezone": p.timezone or "",
        "language": p.language or "en-US",
        "screen_width": p.screen_width or 1920,
        "screen_height": p.screen_height or 1080,
        "webrtc_disabled": p.webrtc_disabled if p.webrtc_disabled is not None else True,
        "notes": p.notes or "",
        "status": "running" if p.id in running_ids else "stopped",
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("")
async def list_profiles(db: Session = Depends(get_db)):
    """获取所有浏览器配置"""
    profiles = (
        db.query(BrowserProfile)
        .outerjoin(Account)
        .order_by(BrowserProfile.id)
        .all()
    )
    running_ids = browser_manager.get_running_ids()
    return {"profiles": [_to_dict(p, running_ids) for p in profiles]}


@router.get("/{profile_id}")
async def get_profile(profile_id: int, db: Session = Depends(get_db)):
    """获取单个浏览器配置"""
    p = db.query(BrowserProfile).get(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="配置不存在")
    running_ids = browser_manager.get_running_ids()
    return _to_dict(p, running_ids)


@router.post("", status_code=201)
async def create_profile(data: BrowserProfileCreate, db: Session = Depends(get_db)):
    """创建浏览器配置"""
    if data.account_id:
        account = db.query(Account).get(data.account_id)
        if not account:
            raise HTTPException(status_code=400, detail="关联账号不存在")

    profile = BrowserProfile(**data.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"id": profile.id, "message": "配置创建成功"}


@router.put("/{profile_id}")
async def update_profile(
    profile_id: int,
    data: BrowserProfileUpdate,
    db: Session = Depends(get_db),
):
    """更新浏览器配置"""
    profile = db.query(BrowserProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="配置不存在")

    if browser_manager.is_running(profile_id):
        raise HTTPException(status_code=400, detail="浏览器运行中, 请先停止再修改")

    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    return {"message": "配置更新成功"}


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    """删除浏览器配置"""
    profile = db.query(BrowserProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="配置不存在")

    if browser_manager.is_running(profile_id):
        raise HTTPException(status_code=400, detail="浏览器运行中, 请先停止再删除")

    db.delete(profile)
    db.commit()

    # 清理浏览器数据目录
    try:
        browser_manager.delete_profile_data(profile_id)
    except Exception:
        pass

    return {"message": "配置已删除"}


@router.post("/{profile_id}/launch")
async def launch_browser(profile_id: int, db: Session = Depends(get_db)):
    """启动浏览器"""
    profile = db.query(BrowserProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="配置不存在")

    try:
        instance = await browser_manager.launch(profile)
        return {"message": "浏览器已启动", "profile_id": instance.profile_id}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动失败: {e}")


@router.post("/{profile_id}/stop")
async def stop_browser(profile_id: int):
    """停止浏览器"""
    try:
        await browser_manager.stop(profile_id)
        return {"message": "浏览器已停止"}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{profile_id}/status")
async def get_browser_status(profile_id: int):
    """获取浏览器运行状态"""
    return browser_manager.get_status(profile_id)


@router.delete("/{profile_id}/data")
async def clear_profile_data(profile_id: int, db: Session = Depends(get_db)):
    """清除浏览器数据（保留配置记录）"""
    profile = db.query(BrowserProfile).get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="配置不存在")

    if browser_manager.is_running(profile_id):
        raise HTTPException(status_code=400, detail="浏览器运行中, 请先停止再清除数据")

    try:
        browser_manager.delete_profile_data(profile_id)
        return {"message": "浏览器数据已清除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除失败: {e}")
