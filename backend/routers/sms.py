"""接码管理路由 - 多提供商支持"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from deps import verify_token
from models.database import get_db
from models.orm import Config, SmsProvider, SmsActivation
from services.sms_api import create_provider

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sms",
    tags=["接码管理"],
    dependencies=[Depends(verify_token)],
)


# ── 工具函数 ──────────────────────────────────────────

def _get_provider_api(db: Session, provider_id: int = None):
    """获取提供商 API 实例"""
    if provider_id:
        p = db.query(SmsProvider).get(provider_id)
    else:
        # 从 config 表读取默认提供商 ID
        row = db.query(Config).filter(Config.key == "default_sms_provider_id").first()
        if row:
            p = db.query(SmsProvider).get(int(row.value))
        else:
            p = db.query(SmsProvider).first()
    if not p:
        raise HTTPException(status_code=400, detail="未找到接码提供商，请先添加配置")
    if not p.api_key:
        raise HTTPException(status_code=400, detail=f"提供商 [{p.name}] 未配置 API Key")
    return create_provider(p.provider_type, p.api_key), p


def _provider_to_dict(p: SmsProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "provider_type": p.provider_type,
        "api_key": p.api_key,
        "default_country": p.default_country,
        "default_service": p.default_service,
        "balance": p.balance,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── 请求模型 ─────────────────────────────────────────

class ProviderCreateBody(BaseModel):
    name: str
    provider_type: str = "herosms"
    api_key: str = ""
    default_country: int = 2
    default_service: str = "go"
    notes: str = ""

class ProviderUpdateBody(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    api_key: Optional[str] = None
    default_country: Optional[int] = None
    default_service: Optional[str] = None
    notes: Optional[str] = None

class RequestNumberBody(BaseModel):
    provider_id: Optional[int] = None
    service: str
    country: int
    operator: Optional[str] = ""
    max_price: Optional[float] = None
    account_id: Optional[int] = None
    account_email: Optional[str] = ""


# ── 提供商 CRUD ──────────────────────────────────────

@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    """获取所有提供商"""
    providers = db.query(SmsProvider).order_by(SmsProvider.id).all()
    return [_provider_to_dict(p) for p in providers]


@router.post("/providers")
def create_provider_route(body: ProviderCreateBody, db: Session = Depends(get_db)):
    """创建提供商"""
    p = SmsProvider(
        name=body.name,
        provider_type=body.provider_type,
        api_key=body.api_key,
        default_country=body.default_country,
        default_service=body.default_service,
        notes=body.notes,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _provider_to_dict(p)


@router.put("/providers/{provider_id}")
def update_provider_route(provider_id: int, body: ProviderUpdateBody, db: Session = Depends(get_db)):
    """更新提供商"""
    p = db.query(SmsProvider).get(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="提供商不存在")

    for field in ["name", "provider_type", "api_key", "default_country", "default_service", "notes"]:
        val = getattr(body, field, None)
        if val is not None:
            setattr(p, field, val)

    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _provider_to_dict(p)


@router.delete("/providers/{provider_id}")
def delete_provider_route(provider_id: int, db: Session = Depends(get_db)):
    """删除提供商"""
    p = db.query(SmsProvider).get(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="提供商不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ── 余额 ─────────────────────────────────────────────

@router.get("/balance")
def get_balance(provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    """查询余额"""
    api, p = _get_provider_api(db, provider_id)
    ok, result = api.get_balance()
    if ok:
        p.balance = result
        p.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"balance": result}
    raise HTTPException(status_code=400, detail=result)


# ── 购买号码 ─────────────────────────────────────────

@router.post("/request-number")
def request_number(body: RequestNumberBody, db: Session = Depends(get_db)):
    """购买号码"""
    api, p = _get_provider_api(db, body.provider_id)
    ok, data = api.get_number(
        service=body.service,
        country=body.country,
        operator=body.operator or "",
        max_price=body.max_price,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=data.get("error", str(data)))

    activation = SmsActivation(
        activation_id=data["activation_id"],
        provider_id=p.id,
        phone_number=data.get("phone_number", ""),
        service=body.service,
        country=body.country,
        operator=data.get("operator", ""),
        cost=data.get("cost", ""),
        status="pending",
        account_id=body.account_id,
        account_email=body.account_email or "",
    )
    db.add(activation)
    db.commit()
    db.refresh(activation)

    return {
        "id": activation.id,
        "activation_id": data["activation_id"],
        "phone_number": data.get("phone_number", ""),
        "cost": data.get("cost", ""),
    }


# ── 查询验证码 ───────────────────────────────────────

@router.get("/status/{activation_id}")
def check_status(activation_id: str, provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    """查询激活状态"""
    record = db.query(SmsActivation).filter(SmsActivation.activation_id == activation_id).first()
    pid = provider_id or (record.provider_id if record else None)
    api, p = _get_provider_api(db, pid)
    status, info = api.get_status(activation_id)

    result = {"status": status, "info": info, "code": ""}

    if status.startswith("RECEIVED:"):
        code = status.split(":", 1)[1]
        result["code"] = code
        result["sms_text"] = info
        if record:
            record.sms_code = code
            record.sms_text = info
            record.status = "code_received"
            record.updated_at = datetime.now(timezone.utc)
            db.commit()
    elif status == "CANCEL":
        if record:
            record.status = "cancelled"
            record.updated_at = datetime.now(timezone.utc)
            db.commit()

    return result


# ── 完成 / 取消 ──────────────────────────────────────

@router.post("/finish/{activation_id}")
def finish_activation(activation_id: str, provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    record = db.query(SmsActivation).filter(SmsActivation.activation_id == activation_id).first()
    pid = provider_id or (record.provider_id if record else None)
    api, _ = _get_provider_api(db, pid)
    result = api.finish(activation_id)
    if record:
        record.status = "finished"
        record.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"result": result}


@router.post("/cancel/{activation_id}")
def cancel_activation(activation_id: str, provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    record = db.query(SmsActivation).filter(SmsActivation.activation_id == activation_id).first()
    pid = provider_id or (record.provider_id if record else None)
    api, _ = _get_provider_api(db, pid)
    result = api.cancel(activation_id)
    if record:
        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"result": result}


# ── 历史记录 ─────────────────────────────────────────

@router.get("/history")
def get_history(page: int = 1, page_size: int = 20, status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(SmsActivation).order_by(SmsActivation.id.desc())
    if status:
        query = query.filter(SmsActivation.status == status)
    total = query.count()
    records = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "records": [
            {
                "id": r.id, "activation_id": r.activation_id, "provider_id": r.provider_id,
                "phone_number": r.phone_number, "service": r.service, "country": r.country,
                "country_name": r.country_name, "operator": r.operator, "cost": r.cost,
                "sms_code": r.sms_code, "sms_text": r.sms_text, "status": r.status,
                "account_id": r.account_id, "account_email": r.account_email, "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in records
        ],
    }


# ── 国家/服务列表 ────────────────────────────────────

@router.get("/countries")
def get_countries(provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    api, _ = _get_provider_api(db, provider_id)
    return api.get_countries()


@router.get("/services")
def get_services(provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    api, _ = _get_provider_api(db, provider_id)
    return api.get_services()


@router.get("/prices-by-service/{service}")
def get_prices_by_service(service: str, provider_id: Optional[int] = None, db: Session = Depends(get_db)):
    """获取某服务在各国的价格和可用数量"""
    api, _ = _get_provider_api(db, provider_id)
    return api.get_prices_by_service(service)
