"""账号路由 - 账号 CRUD、分组/标签查询、TOTP、批量导入"""
import re
import time
import pyotp
from fastapi import APIRouter, HTTPException, Depends

from deps import verify_token, get_account_service
from models.schemas import AccountCreate, AccountUpdate, AccountImportRequest
from services.account import AccountService

router = APIRouter(prefix="/accounts", tags=["账号"], dependencies=[Depends(verify_token)])


def _is_totp_secret(value: str) -> bool:
    """判断字段是否像 TOTP 密钥 (base32 编码, 无空格, 16+ 字符)"""
    if " " in value or len(value) < 12:
        return False
    # base32 字符: A-Z, 2-7 (不区分大小写), 可能有 = 填充
    return bool(re.match(r'^[A-Za-z2-7=]+$', value))


@router.get("")
async def list_accounts(
    search: str = "",
    group: str = "",
    tag: str = "",
    page: int = 1,
    page_size: int = 20,
    owner_only: bool = False,
    svc: AccountService = Depends(get_account_service),
):
    """获取账号列表（支持搜索/筛选/分页）"""
    accounts, total = svc.get_all(search, group, tag, page, page_size, owner_only)
    return {"accounts": accounts, "total": total, "page": page, "page_size": page_size}


@router.get("/groups")
async def list_groups(svc: AccountService = Depends(get_account_service)):
    """获取所有分组"""
    return {"groups": svc.get_all_groups()}


@router.get("/tags")
async def list_tags(svc: AccountService = Depends(get_account_service)):
    """获取所有标签"""
    return {"tags": svc.get_all_tags()}


@router.get("/{account_id}")
async def get_account(account_id: int, svc: AccountService = Depends(get_account_service)):
    """获取单个账号"""
    account = svc.get_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    return account


@router.post("", status_code=201)
async def create_account(
    data: AccountCreate,
    svc: AccountService = Depends(get_account_service),
):
    """创建账号"""
    account_id = svc.create(
        email=data.email,
        password=data.password,
        recovery_email=data.recovery_email,
        totp_secret=data.totp_secret,
        tags=data.tags,
        group_name=data.group_name,
        family_group_id=data.group_id,
        notes=data.notes,
    )
    return {"id": account_id, "message": "账号创建成功"}


@router.post("/import", status_code=201)
async def import_accounts(
    data: AccountImportRequest,
    svc: AccountService = Depends(get_account_service),
):
    """批量导入账号

    支持多种格式 (用 ---- 分隔), 智能识别字段类型:
    - 格式1: 邮箱----密码----辅助邮箱----2FA密钥----短信验证链接
    - 格式2: 邮箱----密码----辅助邮箱----webhook链接
    - 格式3: 邮箱----密码----辅助邮箱
    - 格式4: 邮箱----密码

    字段识别规则 (第3个字段起):
    - 含 @ → 辅助邮箱
    - 以 http:// 或 https:// 开头 → 链接 (记录到备注)
    - 其他 → 2FA 密钥
    """
    lines = [line.strip() for line in data.text.strip().splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="导入内容为空")

    results = {"success": 0, "skipped": 0, "failed": 0, "details": []}

    for line in lines:
        # 自动检测分隔符: ---- 或 |
        if "----" in line:
            parts = [p.strip() for p in line.split("----")]
        else:
            parts = [p.strip() for p in line.split("|")]
        if not parts or not parts[0]:
            results["failed"] += 1
            results["details"].append({"line": line, "status": "failed", "reason": "空行"})
            continue

        # 第1个字段: 邮箱, 第2个字段: 密码
        email = parts[0]
        password = parts[1] if len(parts) > 1 else ""

        # 第3个字段起: 智能识别
        recovery_email = ""
        totp_secret = ""
        links = []
        extra_notes = []

        for field in parts[2:]:
            if not field:
                continue
            if "@" in field and not field.startswith("http"):
                # 含 @ 且不是 URL → 辅助邮箱
                recovery_email = field
            elif field.startswith("http://") or field.startswith("https://"):
                # URL → 链接
                links.append(field)
            elif _is_totp_secret(field) and not totp_secret:
                # 像 TOTP 密钥 (base32, 无空格, 16+字符) 且还没设过
                totp_secret = field
            else:
                # 其他 (国家名、备注等) → 记入备注
                extra_notes.append(field)

        # 检查邮箱是否已存在
        existing = svc.find_by_email(email)
        if existing:
            results["skipped"] += 1
            results["details"].append({"email": email, "status": "skipped", "reason": "邮箱已存在"})
            continue

        # 构造备注: 链接和额外信息记录到 notes
        notes = data.notes or ""
        if links:
            links_text = "\n".join(links)
            notes = f"验证链接: {links_text}" + (f"\n{notes}" if notes else "")
        if extra_notes:
            extra_text = ", ".join(extra_notes)
            notes = (f"{notes}\n" if notes else "") + extra_text

        try:
            account_id = svc.create(
                email=email,
                password=password,
                recovery_email=recovery_email,
                totp_secret=totp_secret,
                tags=data.tags or "",
                group_name=data.group_name or "",
                notes=notes,
            )
            results["success"] += 1
            results["details"].append({"email": email, "status": "success", "id": account_id})
        except Exception as e:
            results["failed"] += 1
            results["details"].append({"email": email, "status": "failed", "reason": str(e)})

    return {
        "message": f"导入完成: 成功 {results['success']}, 跳过 {results['skipped']}, 失败 {results['failed']}",
        **results,
    }


@router.put("/{account_id}")
async def update_account(
    account_id: int,
    data: AccountUpdate,
    svc: AccountService = Depends(get_account_service),
):
    """更新账号"""
    svc.update(
        account_id=account_id,
        email=data.email,
        password=data.password,
        recovery_email=data.recovery_email,
        totp_secret=data.totp_secret,
        tags=data.tags,
        group_name=data.group_name,
        family_group_id=data.group_id,
        notes=data.notes,
    )
    return {"message": "账号更新成功"}


@router.delete("/{account_id}")
async def delete_account(account_id: int, svc: AccountService = Depends(get_account_service)):
    """删除账号"""
    svc.delete(account_id)
    return {"message": "账号删除成功"}


@router.get("/{account_id}/totp")
async def get_totp_code(account_id: int, svc: AccountService = Depends(get_account_service)):
    """获取账号的 TOTP 验证码"""
    account = svc.get_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not account.get("totp_secret"):
        raise HTTPException(status_code=400, detail="该账号未设置2FA密钥")

    try:
        totp = pyotp.TOTP(account["totp_secret"].replace(' ', ''))
        code = totp.now()
        remaining = 30 - (int(time.time()) % 30)
        return {"code": code, "remaining": remaining, "formatted": f"{code[:3]} {code[3:]}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"生成验证码失败: {e}")
