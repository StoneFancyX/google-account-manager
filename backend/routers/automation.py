"""自动化操作路由 - Google 登录 / 家庭组管理 (REST + WebSocket)"""
import asyncio
import json
import logging
import queue
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from deps import verify_token, state
from models.database import get_db, SessionLocal
from models.orm import Account, BrowserProfile, Group
from services.browser import browser_manager
from services.automation import (
    run_auto_login,
    run_create_family_group,
    run_send_family_invite,
    run_accept_family_invite,
    run_remove_family_member,
    run_leave_family_group,
    run_discover_family_group,
    discover_family_by_cookies,
    run_oauth,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/automation",
    tags=["自动化"],
    dependencies=[Depends(verify_token)],
)


# ---- 请求模型 ----

class AutoLoginRequest(BaseModel):
    account_id: int


class FamilyInviteRequest(BaseModel):
    account_id: int
    invite_email: str


class FamilyMemberRequest(BaseModel):
    account_id: int
    member_email: str


class AccountActionRequest(BaseModel):
    account_id: int


# ---- 工具函数 ----

def _get_profile_id(account_id: int, db: Session) -> int:
    """根据 account_id 获取对应 browser_profile, 要求浏览器已启动"""
    profile = (
        db.query(BrowserProfile)
        .filter(BrowserProfile.account_id == account_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=400, detail="该账号没有浏览器配置, 请先启动浏览器")

    if not browser_manager.is_running(profile.id):
        raise HTTPException(status_code=400, detail="浏览器未启动, 请先启动浏览器")

    return profile.id


def _decrypt(value: str) -> str:
    """获取数据库字段值 (不再加密, 直接返回)"""
    return value or ""


def _save_cookies(account_id: int, profile_id: int):
    """从运行中的浏览器提取 cookies 并保存到数据库"""
    try:
        cookies = browser_manager.get_cookies(profile_id)
        if not cookies:
            return
        db = SessionLocal()
        try:
            account = db.query(Account).get(account_id)
            if account:
                account.cookies_json = json.dumps(cookies)
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[cookies] 已保存 {len(cookies)} 个 cookies → account #{account_id}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[cookies] 保存失败: {e}")


def _save_oauth_credential(account_id: int, credential: dict):
    """保存 OAuth 认证 JSON 到数据库"""
    try:
        db = SessionLocal()
        try:
            account = db.query(Account).get(account_id)
            if account:
                # 如果凭证中没有 email, 用账号的 email
                if "email" not in credential:
                    credential["email"] = account.email
                account.oauth_credential_json = json.dumps(credential)
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[oauth] 已保存 OAuth 凭证 → account #{account_id}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[oauth] 保存 OAuth 凭证失败: {e}")


def _save_country(account_id: int, country: str, country_cn: str = ""):
    """保存账号地区信息到数据库"""
    if not country:
        return
    try:
        db = SessionLocal()
        try:
            account = db.query(Account).get(account_id)
            if account and (account.country != country or account.country_cn != country_cn):
                account.country = country
                account.country_cn = country_cn
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[country] 已保存地区 → account #{account_id}: {country} ({country_cn})")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[country] 保存地区失败: {e}")


def _save_subscription_status(account_id: int, subscription_status: str, subscription_expiry: str = ""):
    """保存订阅状态到数据库，主号 Ultra 自动传播给同组所有子号"""
    if not subscription_status:
        return
    try:
        db = SessionLocal()
        try:
            account = db.query(Account).get(account_id)
            if not account:
                return
            changed = False
            if account.subscription_status != subscription_status:
                account.subscription_status = subscription_status
                changed = True
            if subscription_expiry and account.subscription_expiry != subscription_expiry:
                account.subscription_expiry = subscription_expiry
                changed = True
            if changed:
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[subscription] account #{account_id} → {subscription_status} {subscription_expiry}")

            # 主号 Ultra → 传播给同组所有子号
            if subscription_status == "ultra" and account.family_group_id:
                group = db.query(Group).get(account.family_group_id)
                if group and group.main_account_id == account.id:
                    members = (
                        db.query(Account)
                        .filter(Account.family_group_id == group.id, Account.id != account.id)
                        .all()
                    )
                    for m in members:
                        m_changed = False
                        if m.subscription_status != subscription_status:
                            m.subscription_status = subscription_status
                            m_changed = True
                        if subscription_expiry and m.subscription_expiry != subscription_expiry:
                            m.subscription_expiry = subscription_expiry
                            m_changed = True
                        if m_changed:
                            m.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    if members:
                        logger.info(f"[subscription] Ultra 已传播给 {len(members)} 个子号")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[subscription] 保存失败: {e}")


# ---- 家庭组 → 分组自动同步 ----

def _sync_group_after_action(action: str, account_id: int, success: bool, result_msg: str, extra: dict = None):
    """自动化操作成功后，同步家庭组关系到数据库分组

    action: 操作类型 (family-create / family-accept / family-remove / family-leave)
    account_id: 当前操作账号的 ID
    success: 操作是否成功
    extra: 额外参数, 如 invite_email / member_email
    """
    if not success:
        return

    db = SessionLocal()
    try:
        account = db.query(Account).get(account_id)
        if not account:
            return

        if action == "family-create":
            # 创建家庭组 → 新建分组, 设当前账号为管理员
            # 检查该账号是否已在某个分组中
            if account.family_group_id:
                logger.info(f"[sync_group] 账号 {account.email} 已在分组 {account.family_group_id} 中, 跳过创建")
                return
            group = Group(name=f"{account.email} 的家庭组")
            db.add(group)
            db.flush()  # 获取 group.id
            group.main_account_id = account.id
            account.family_group_id = group.id
            account.updated_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"[sync_group] 已创建分组 #{group.id} 并设置 {account.email} 为管理员")

        elif action == "family-accept":
            # 接受邀请 → 当前账号加入邀请方的分组
            joined_group_id = None
            if account.family_group_id:
                logger.info(f"[sync_group] 账号 {account.email} 已在分组 {account.family_group_id} 中, 跳过")
                joined_group_id = account.family_group_id
            else:
                # 方式1: extra 中指定了 group_id (替换成员场景)
                group_id = (extra or {}).get("group_id")
                if group_id:
                    group = db.query(Group).get(group_id)
                    if group:
                        account.family_group_id = group_id
                        account.updated_at = datetime.now(timezone.utc)
                        db.commit()
                        joined_group_id = group_id
                        logger.info(f"[sync_group] 已将 {account.email} 加入分组 #{group_id}")

                # 方式2: extra 中指定了 manager_account_id (管理员账号ID)
                if not joined_group_id:
                    manager_id = (extra or {}).get("manager_account_id")
                    if manager_id:
                        manager = db.query(Account).get(manager_id)
                        if manager and manager.family_group_id:
                            account.family_group_id = manager.family_group_id
                            account.updated_at = datetime.now(timezone.utc)
                            db.commit()
                            joined_group_id = manager.family_group_id
                            logger.info(f"[sync_group] 已将 {account.email} 加入管理员 {manager.email} 的分组 #{manager.family_group_id}")

                # 方式3: 兜底 - 查找有管理员且成员未满的分组
                if not joined_group_id:
                    logger.info(f"[sync_group] 接受邀请: 账号 {account.email} 无法自动关联分组 (未提供 group_id 或 manager_account_id)")
                    from sqlalchemy import func
                    groups = db.query(Group).filter(Group.main_account_id.isnot(None)).all()
                    for g in groups:
                        member_count = db.query(func.count(Account.id)).filter(Account.family_group_id == g.id).scalar()
                        if member_count < 6:
                            account.family_group_id = g.id
                            account.updated_at = datetime.now(timezone.utc)
                            db.commit()
                            joined_group_id = g.id
                            logger.info(f"[sync_group] 兜底: 已将 {account.email} 加入分组 #{g.id} ({g.name})")
                            break
                    if not joined_group_id:
                        logger.warning(f"[sync_group] 接受邀请: 未找到可加入的分组")

            # 继承主号 Ultra 订阅状态
            if joined_group_id:
                group = db.query(Group).get(joined_group_id)
                if group and group.main_account_id:
                    main_acc = db.query(Account).get(group.main_account_id)
                    if main_acc and main_acc.subscription_status == "ultra":
                        account.subscription_status = main_acc.subscription_status
                        account.subscription_expiry = main_acc.subscription_expiry or ""
                        account.updated_at = datetime.now(timezone.utc)
                        db.commit()
                        logger.info(f"[sync_group] {account.email} 继承主号 Ultra 订阅")

        elif action == "family-remove":
            # 移除成员 → 从分组中移除被移除的账号 + 清除订阅状态
            member_email = (extra or {}).get("member_email", "")
            if not member_email:
                return
            member = db.query(Account).filter(Account.email == member_email).first()
            if member and member.family_group_id:
                old_group_id = member.family_group_id
                member.family_group_id = None
                member.subscription_status = ""
                member.subscription_expiry = ""
                member.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[sync_group] 已将 {member_email} 从分组 #{old_group_id} 中移除, 清除订阅状态")

        elif action == "family-leave":
            # 退出/删除家庭组
            if not account.family_group_id:
                return
            group_id = account.family_group_id
            group = db.query(Group).get(group_id)
            if not group:
                return

            if group.main_account_id == account.id:
                # 管理员删除 → 删除整个分组, 清除所有成员的 family_group_id + 订阅状态
                db.query(Account).filter(Account.family_group_id == group_id).update(
                    {"family_group_id": None, "subscription_status": "", "subscription_expiry": "", "updated_at": datetime.now(timezone.utc)}
                )
                db.delete(group)
                db.commit()
                logger.info(f"[sync_group] 管理员 {account.email} 删除了分组 #{group_id}, 已清除所有成员订阅状态")
            else:
                # 成员退出 → 仅移除自己 + 清除订阅状态
                account.family_group_id = None
                account.subscription_status = ""
                account.subscription_expiry = ""
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[sync_group] 成员 {account.email} 退出了分组 #{group_id}, 已清除订阅状态")

    except Exception as e:
        logger.error(f"[sync_group] 同步分组失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _sync_group_from_discover(account_id: int, discover_result):
    """根据家庭组发现结果自动同步数据库分组关系

    discover_result: FamilyDiscoverResult (has_group, role, members)
    """
    if not discover_result or not discover_result.success:
        return

    db = SessionLocal()
    try:
        account = db.query(Account).get(account_id)
        if not account:
            return

        if not discover_result.has_group:
            # 没有家庭组 → 清除关联 + 订阅状态
            if account.family_group_id:
                old_gid = account.family_group_id
                account.family_group_id = None
                account.subscription_status = ""
                account.subscription_expiry = ""
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[discover_sync] {account.email} 已不在家庭组, 清除分组 #{old_gid} + 订阅状态")
            else:
                logger.info(f"[discover_sync] {account.email} 无家庭组, 无需更新")
            return

        # 有家庭组
        if discover_result.role == "manager":
            # 管理员 → 确保有 Group, 且 main_account_id 是自己
            if account.family_group_id:
                group = db.query(Group).get(account.family_group_id)
                if group and group.main_account_id == account.id:
                    # 更新 member_count
                    group.member_count = discover_result.member_count
                    group.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.info(f"[discover_sync] {account.email} 已是分组 #{group.id} 管理员, 更新成员数={discover_result.member_count}")
                    # 同步成员
                    _sync_members_from_discover(db, group.id, discover_result.members)
                    return
                # 关联的分组不存在或管理员不是自己 → 清除旧关联后重建
                logger.info(f"[discover_sync] {account.email} 旧分组 #{account.family_group_id} 无效, 将重建")
                account.family_group_id = None

            # 先查找是否已有自己作为管理员的空分组 (避免重复创建)
            existing_group = db.query(Group).filter(Group.main_account_id == account.id).first()
            if existing_group:
                group = existing_group
                group.member_count = discover_result.member_count
                group.name = f"{account.email} 的家庭组"
                group.updated_at = datetime.now(timezone.utc)
                account.family_group_id = group.id
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[discover_sync] 复用已有分组 #{group.id} 给管理员 {account.email}")
            else:
                # 创建新组
                group = Group(name=f"{account.email} 的家庭组", member_count=discover_result.member_count)
                db.add(group)
                db.flush()
                group.main_account_id = account.id
                account.family_group_id = group.id
                account.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[discover_sync] 为管理员 {account.email} 创建分组 #{group.id}")
            # 同步成员
            _sync_members_from_discover(db, group.id, discover_result.members)

        elif discover_result.role == "member":
            # 成员 → 找到管理员所在的组并加入
            if account.family_group_id:
                logger.info(f"[discover_sync] {account.email} 已在分组 #{account.family_group_id} 中")
                return
            # 尝试通过成员列表中的管理员名字匹配系统中的账号
            manager_names = [m["name"] for m in discover_result.members if m.get("role") == "manager"]
            for mname in manager_names:
                mname_lower = mname.lower()
                # 在系统账号中查找邮箱前缀匹配的管理员
                candidates = db.query(Account).filter(Account.family_group_id.isnot(None)).all()
                for c in candidates:
                    if c.email.split("@")[0].lower() in mname_lower or mname_lower in c.email.lower():
                        group = db.query(Group).get(c.family_group_id)
                        if group and group.main_account_id == c.id:
                            account.family_group_id = group.id
                            account.updated_at = datetime.now(timezone.utc)
                            db.commit()
                            logger.info(f"[discover_sync] 成员 {account.email} 加入管理员 {c.email} 的分组 #{group.id}")
                            return
            logger.info(f"[discover_sync] 成员 {account.email} 未找到匹配的管理员分组")

    except Exception as e:
        logger.error(f"[discover_sync] 同步失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _sync_members_from_discover(db, group_id: int, members: list):
    """根据发现的成员列表, 同步数据库中的成员关系

    members: [{"name": "xxx", "email": "xxx@gmail.com", "role": "member"/"manager"/"pending"}]
    - 按邮箱精确匹配已有账号并关联
    - 不存在的成员自动创建账号 (仅邮箱)
    - 移除不在 discover 结果中的旧成员 (清除 family_group_id)
    - pending 成员标记 is_family_pending=True
    """
    try:
        # 收集 discover 结果中所有成员邮箱 (含管理员和 pending)
        discovered_emails = set()
        for m in members:
            email = m.get("email", "").strip().lower()
            if email:
                discovered_emails.add(email)

        # 第一步: 移除不在 discover 结果中的旧成员
        # (管理员通过 Group.main_account_id 管理, 这里只处理 family_group_id 关联)
        old_members = db.query(Account).filter(Account.family_group_id == group_id).all()
        for old_acc in old_members:
            if old_acc.email.lower() not in discovered_emails:
                logger.info(f"[discover_sync] 成员 {old_acc.email} 不在 discover 结果中, 从分组 #{group_id} 移除")
                old_acc.family_group_id = None
                old_acc.is_family_pending = False
                old_acc.subscription_status = ""
                old_acc.subscription_expiry = ""
                old_acc.updated_at = datetime.now(timezone.utc)
        db.commit()

        # 第二步: 添加/关联 discover 中的成员 (含 pending)
        for m in members:
            if m.get("role") == "manager":
                # 管理员: 确保 pending 标记清除
                email = m.get("email", "").strip()
                if email:
                    acc = db.query(Account).filter(Account.email.ilike(email)).first()
                    if acc and acc.is_family_pending:
                        acc.is_family_pending = False
                        acc.updated_at = datetime.now(timezone.utc)
                        db.commit()
                continue
            email = m.get("email", "").strip()
            if not email:
                logger.info(f"[discover_sync] 成员 {m.get('name', '?')} 无邮箱, 跳过")
                continue

            is_pending = m.get("role") == "pending"

            # 按邮箱精确匹配
            acc = db.query(Account).filter(Account.email.ilike(email)).first()
            if acc:
                # 已有账号 → 关联到家庭组 + 更新 pending 状态
                changed = False
                if acc.family_group_id != group_id:
                    acc.family_group_id = group_id
                    changed = True
                if acc.is_family_pending != is_pending:
                    acc.is_family_pending = is_pending
                    changed = True
                if changed:
                    acc.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    status_str = "待接受" if is_pending else "正式成员"
                    logger.info(f"[discover_sync] 已有成员 {acc.email} 关联到分组 #{group_id} ({status_str})")
            else:
                # 不存在 → 创建新账号 (仅邮箱)
                new_acc = Account(email=email, family_group_id=group_id, is_family_pending=is_pending)
                db.add(new_acc)
                db.commit()
                status_str = "待接受" if is_pending else "正式成员"
                logger.info(f"[discover_sync] 新建成员账号 {email} 并关联到分组 #{group_id} ({status_str})")
    except Exception as e:
        logger.error(f"[discover_sync] 同步成员失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# ---- 自动登录 ----

@router.post("/login")
async def auto_login(req: AutoLoginRequest, db: Session = Depends(get_db)):
    """自动登录 Google 账号"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    profile_id = _get_profile_id(req.account_id, db)

    # 从 notes 中提取验证链接
    from services.verification import extract_verification_link
    verification_url = extract_verification_link(account.notes or "") or ""

    result = await run_auto_login(
        profile_id=profile_id,
        email=account.email,
        password=_decrypt(account.password),
        totp_secret=_decrypt(account.totp_secret) or "",
        recovery_email=_decrypt(account.recovery_email) or "",
        verification_url=verification_url,
    )
    # 登录成功后保存 cookies
    if result.success:
        _save_cookies(req.account_id, profile_id)
    return result.to_dict()


# ---- 家庭组操作 ----

@router.post("/family/create")
async def create_family_group(req: AccountActionRequest, db: Session = Depends(get_db)):
    """创建家庭组"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    profile_id = _get_profile_id(req.account_id, db)
    result = await run_create_family_group(profile_id)
    if result.success:
        _save_cookies(req.account_id, profile_id)
    _sync_group_after_action("family-create", req.account_id, result.success, result.message)
    return result.to_dict()


@router.post("/family/invite")
async def send_family_invite(req: FamilyInviteRequest, db: Session = Depends(get_db)):
    """发送家庭组邀请"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    profile_id = _get_profile_id(req.account_id, db)
    result = await run_send_family_invite(profile_id, req.invite_email)
    if result.success:
        _save_cookies(req.account_id, profile_id)
    return result.to_dict()


@router.post("/family/accept")
async def accept_family_invite(req: AccountActionRequest, db: Session = Depends(get_db)):
    """接受家庭组邀请"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    profile_id = _get_profile_id(req.account_id, db)
    result = await run_accept_family_invite(profile_id)
    if result.success:
        _save_cookies(req.account_id, profile_id)
    _sync_group_after_action("family-accept", req.account_id, result.success, result.message)
    return result.to_dict()


@router.post("/family/remove-member")
async def remove_family_member(req: FamilyMemberRequest, db: Session = Depends(get_db)):
    """移除家庭组成员 (需要管理员权限, 可能需要密码 + 2FA 重验证)"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    profile_id = _get_profile_id(req.account_id, db)
    password = _decrypt(account.password)
    totp_secret = _decrypt(account.totp_secret) or ""
    result = await run_remove_family_member(profile_id, req.member_email, password=password, totp_secret=totp_secret)
    if result.success:
        _save_cookies(req.account_id, profile_id)
    _sync_group_after_action("family-remove", req.account_id, result.success, result.message, {"member_email": req.member_email})
    return result.to_dict()


@router.post("/family/leave")
async def leave_family_group(req: AccountActionRequest, db: Session = Depends(get_db)):
    """退出/删除家庭组 (管理员删除需要密码 + 2FA 重验证)"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    profile_id = _get_profile_id(req.account_id, db)
    password = _decrypt(account.password)
    totp_secret = _decrypt(account.totp_secret) or ""
    result = await run_leave_family_group(profile_id, password=password, totp_secret=totp_secret)
    if result.success:
        _save_cookies(req.account_id, profile_id)
    _sync_group_after_action("family-leave", req.account_id, result.success, result.message)
    return result.to_dict()


# ---- 家庭组同步 (纯 HTTP, 不需要浏览器) ----

@router.post("/family/discover")
async def discover_family(req: AccountActionRequest, db: Session = Depends(get_db)):
    """同步家庭组状态 (优先用保存的 cookies, cookies 过期自动登录刷新)"""
    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 获取浏览器 profile_id (可选, 用于 cookies 过期时的回退)
    profile = (
        db.query(BrowserProfile)
        .filter(BrowserProfile.account_id == req.account_id)
        .first()
    )
    browser_profile_id = profile.id if profile else None

    # 解密凭证 (用于 cookies 过期时自动登录)
    email = account.email
    password = _decrypt(account.password)
    totp_secret = _decrypt(account.totp_secret) or ""
    recovery_email = _decrypt(account.recovery_email) or ""

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        discover_family_by_cookies,
        req.account_id,
        account.cookies_json or "",
        browser_profile_id,
        email,
        password,
        totp_secret,
        recovery_email,
    )

    # 同步分组关系
    if result.success:
        _sync_group_from_discover(req.account_id, result)
        # 保存订阅状态
        _save_subscription_status(req.account_id, result.subscription_status, result.subscription_expiry)
        # 保存地区信息
        _save_country(req.account_id, result.country, result.country_cn)

    return result.to_dict()


# ---- OAuth 凭证 API ----

@router.get("/oauth/credential/{account_id}")
async def get_oauth_credential(account_id: int, db: Session = Depends(get_db)):
    """获取账号的 OAuth 认证 JSON"""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not account.oauth_credential_json:
        raise HTTPException(status_code=404, detail="该账号暂无 OAuth 凭证")
    return json.loads(account.oauth_credential_json)


@router.get("/oauth/credential/{account_id}/download")
async def download_oauth_credential(account_id: int, db: Session = Depends(get_db)):
    """下载 OAuth 认证 JSON 文件"""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not account.oauth_credential_json:
        raise HTTPException(status_code=404, detail="该账号暂无 OAuth 凭证")

    email = account.email or "unknown"
    filename = f"antigravity-{email}.json"
    content = account.oauth_credential_json
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# WebSocket 实时操作 endpoint
# ============================================================

# 单独创建不带 auth 依赖的 ws router (WebSocket 通过 query param 认证)
ws_router = APIRouter(tags=["自动化"])


@ws_router.websocket("/ws/automation")
async def automation_websocket(ws: WebSocket):
    """
    WebSocket 实时自动化操作

    客户端发送:
      {"action": "login", "account_id": 1}
      {"action": "family-create", "account_id": 1}
      {"action": "family-invite", "account_id": 1, "invite_email": "xxx@gmail.com"}
      {"action": "family-accept", "account_id": 1}
      {"action": "family-remove", "account_id": 1, "member_email": "xxx@gmail.com"}
      {"action": "family-leave", "account_id": 1}

    服务端实时推送:
      {"type": "step", "step": 1, "name": "打开登录页", "status": "running", ...}
      {"type": "step", "step": 1, "name": "打开登录页", "status": "ok", "message": "...", ...}
      {"type": "result", "success": true, "message": "登录成功", "duration_ms": 12345}
    """
    # 认证: 从 query param 获取 token
    token = ws.query_params.get("token", "")
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return

    from deps import verify_ws_token
    if not verify_ws_token(token):
        await ws.close(code=4001, reason="Invalid token")
        return

    await ws.accept()
    logger.info("WebSocket automation client connected")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = data.get("action", "")
            account_id = data.get("account_id")

            if not account_id:
                await ws.send_json({"type": "error", "message": "缺少 account_id"})
                continue

            # 获取账号和 profile
            db = SessionLocal()
            try:
                account = db.query(Account).get(account_id)
                if not account:
                    await ws.send_json({"type": "error", "message": "账号不存在"})
                    continue

                profile = (
                    db.query(BrowserProfile)
                    .filter(BrowserProfile.account_id == account_id)
                    .first()
                )
                # family-discover 不强制要求浏览器运行
                if action == "family-discover":
                    profile_id = profile.id if profile else None
                elif not profile or not browser_manager.is_running(profile.id):
                    await ws.send_json({"type": "error", "message": "浏览器未启动"})
                    continue
                else:
                    profile_id = profile.id
                email = account.email
                password = _decrypt(account.password)
                totp_secret = _decrypt(account.totp_secret) or ""
                recovery_email = _decrypt(account.recovery_email) or ""
                # 从 notes 中提取验证链接
                from services.verification import extract_verification_link
                verification_url = extract_verification_link(account.notes or "") or ""
            finally:
                db.close()

            # 用 queue 实现线程安全的步骤推送
            msg_queue: queue.Queue = queue.Queue()

            def on_step(step_data: dict):
                msg_queue.put(step_data)

            # 启动自动化任务
            task = None
            if action == "login":
                task = asyncio.ensure_future(
                    run_auto_login(profile_id, email, password, totp_secret, recovery_email, verification_url, on_step=on_step)
                )
            elif action == "family-create":
                task = asyncio.ensure_future(
                    run_create_family_group(profile_id, on_step=on_step)
                )
            elif action == "family-invite":
                invite_email = data.get("invite_email", "")
                if not invite_email:
                    await ws.send_json({"type": "error", "message": "缺少 invite_email"})
                    continue
                task = asyncio.ensure_future(
                    run_send_family_invite(profile_id, invite_email, on_step=on_step)
                )
            elif action == "family-batch-invite":
                invite_emails_raw = data.get("invite_emails", "")
                invite_emails = [e.strip() for e in invite_emails_raw.split(",") if e.strip()]
                if not invite_emails:
                    await ws.send_json({"type": "error", "message": "缺少邀请邮箱"})
                    continue

                total = len(invite_emails)
                success_count = 0
                fail_list = []

                for i, invite_email in enumerate(invite_emails):
                    step_offset = i * 100
                    def on_step_batch(d, offset=step_offset):
                        if d.get("step"):
                            d = {**d, "step": d["step"] + offset}
                        msg_queue.put(d)

                    on_step_batch({"type": "step", "name": f"--- 邀请 {invite_email} ({i+1}/{total}) ---", "status": "info", "message": invite_email})

                    task = asyncio.ensure_future(
                        run_send_family_invite(profile_id, invite_email, on_step=on_step_batch)
                    )
                    # drain queue while task runs
                    while not task.done():
                        try:
                            m = msg_queue.get_nowait()
                            if m.get("type") != "result":
                                await ws.send_json(m)
                        except queue.Empty:
                            await asyncio.sleep(0.1)
                    while not msg_queue.empty():
                        m = msg_queue.get_nowait()
                        if m.get("type") != "result":
                            await ws.send_json(m)

                    invite_result = task.result() if not task.exception() else None
                    if invite_result and invite_result.success:
                        success_count += 1
                        _sync_group_after_action("family-invite", account_id, True, invite_result.message, {"invite_email": invite_email})
                    else:
                        err = invite_result.message if invite_result else str(task.exception())
                        fail_list.append(f"{invite_email}: {err}")

                # 汇总结果
                if fail_list:
                    summary = f"批量邀请完成: 成功 {success_count}/{total}, 失败: {'; '.join(fail_list)}"
                    await ws.send_json({"type": "result", "success": success_count > 0, "message": summary, "duration_ms": 0})
                else:
                    await ws.send_json({"type": "result", "success": True, "message": f"批量邀请完成: 全部成功 ({total})", "duration_ms": 0})
                continue
            elif action == "family-accept":
                task = asyncio.ensure_future(
                    run_accept_family_invite(profile_id, on_step=on_step)
                )
            elif action == "family-remove":
                member_email = data.get("member_email", "")
                if not member_email:
                    await ws.send_json({"type": "error", "message": "缺少 member_email"})
                    continue
                task = asyncio.ensure_future(
                    run_remove_family_member(profile_id, member_email, password, totp_secret, on_step=on_step)
                )
            elif action == "family-batch-remove":
                member_emails_raw = data.get("member_emails", "")
                member_emails = [e.strip() for e in member_emails_raw.split(",") if e.strip()]
                if not member_emails:
                    await ws.send_json({"type": "error", "message": "缺少成员邮箱"})
                    continue

                total = len(member_emails)
                success_count = 0
                fail_list = []

                for i, member_email in enumerate(member_emails):
                    step_offset = i * 100
                    def on_step_batch(d, offset=step_offset):
                        if d.get("step"):
                            d = {**d, "step": d["step"] + offset}
                        msg_queue.put(d)

                    on_step_batch({"type": "step", "name": f"--- 移除 {member_email} ({i+1}/{total}) ---", "status": "info", "message": member_email})

                    task = asyncio.ensure_future(
                        run_remove_family_member(profile_id, member_email, password, totp_secret, on_step=on_step_batch)
                    )
                    while not task.done():
                        try:
                            m = msg_queue.get_nowait()
                            if m.get("type") != "result":
                                await ws.send_json(m)
                        except queue.Empty:
                            await asyncio.sleep(0.1)
                    while not msg_queue.empty():
                        m = msg_queue.get_nowait()
                        if m.get("type") != "result":
                            await ws.send_json(m)

                    remove_result = task.result() if not task.exception() else None
                    if remove_result and remove_result.success:
                        success_count += 1
                        _sync_group_after_action("family-remove", account_id, True, remove_result.message, {"member_email": member_email})
                    else:
                        err = remove_result.message if remove_result else str(task.exception())
                        fail_list.append(f"{member_email}: {err}")

                if fail_list:
                    summary = f"批量移除完成: 成功 {success_count}/{total}, 失败: {'; '.join(fail_list)}"
                    await ws.send_json({"type": "result", "success": success_count > 0, "message": summary, "duration_ms": 0})
                else:
                    await ws.send_json({"type": "result", "success": True, "message": f"批量移除完成: 全部成功 ({total})", "duration_ms": 0})
                continue
            elif action == "family-leave":
                task = asyncio.ensure_future(
                    run_leave_family_group(profile_id, password, totp_secret, on_step=on_step)
                )
            elif action == "family-discover":
                # 发现家庭组关系 → cookies 过期自动登录刷新
                db_d = SessionLocal()
                try:
                    acc_d = db_d.query(Account).get(account_id)
                    saved_cookies = acc_d.cookies_json if acc_d else ""
                finally:
                    db_d.close()

                loop = asyncio.get_event_loop()
                dr = await loop.run_in_executor(
                    None,
                    discover_family_by_cookies,
                    account_id,
                    saved_cookies or "",
                    profile_id,
                    email,
                    password,
                    totp_secret,
                    recovery_email,
                )

                if dr and dr.success:
                    _sync_group_from_discover(account_id, dr)
                    _save_subscription_status(account_id, dr.subscription_status, dr.subscription_expiry)
                    _save_country(account_id, dr.country, dr.country_cn)
                await ws.send_json({
                    "type": "result",
                    "success": dr.success if dr else False,
                    "message": dr.message if dr else "未知错误",
                    "duration_ms": 0,
                })
                continue
            elif action == "oauth":
                task = asyncio.ensure_future(
                    run_oauth(profile_id, on_step=on_step, password=password, totp_secret=totp_secret)
                )
            elif action == "phone-verify":
                validation_url = data.get("validation_url", "")
                if not validation_url:
                    await ws.send_json({"type": "error", "message": "缺少 validation_url"})
                    continue
                from services.oauth import auto_phone_verify_sync
                loop = asyncio.get_event_loop()
                task = asyncio.ensure_future(
                    loop.run_in_executor(None, auto_phone_verify_sync, page, validation_url, on_step)
                )
            elif action == "family-replace":
                old_email = data.get("old_email", "")
                new_email = data.get("new_email", "")
                if not old_email or not new_email:
                    await ws.send_json({"type": "error", "message": "缺少 old_email 或 new_email"})
                    continue

                # 步骤偏移: 避免不同阶段的步骤编号冲突导致前端覆盖
                step_offset = [0]
                def on_step_replace(data):
                    """带偏移量的 on_step, 避免子操作步骤编号冲突"""
                    if data.get("step"):
                        data = {**data, "step": data["step"] + step_offset[0]}
                    msg_queue.put(data)

                # 辅助: 转发子操作步骤消息, 过滤掉子操作的 result 消息 (避免前端提前关闭 WS)
                async def _drain_queue(tsk, mq):
                    while not tsk.done():
                        try:
                            m = mq.get_nowait()
                            if m.get("type") != "result":
                                await ws.send_json(m)
                        except queue.Empty:
                            await asyncio.sleep(0.1)
                    while not mq.empty():
                        m = mq.get_nowait()
                        if m.get("type") != "result":
                            await ws.send_json(m)

                # --- Phase 1: 移除旧成员 ---
                step_offset[0] = 0
                on_step_replace({"type": "step", "name": "--- 阶段1: 移除旧成员 ---", "status": "info", "message": old_email})
                task = asyncio.ensure_future(
                    run_remove_family_member(profile_id, old_email, password, totp_secret, on_step=on_step_replace)
                )
                await _drain_queue(task, msg_queue)

                remove_result = task.result() if not task.exception() else None
                if not remove_result or not remove_result.success:
                    err_msg = f"移除旧成员失败: {remove_result.message if remove_result else str(task.exception())}"
                    await ws.send_json({"type": "result", "success": False, "message": err_msg, "duration_ms": 0})
                    _sync_group_after_action("family-remove", account_id, False, err_msg, {"member_email": old_email})
                    continue

                _sync_group_after_action("family-remove", account_id, True, remove_result.message, {"member_email": old_email})
                await ws.send_json({"type": "step", "name": "移除旧成员完成", "status": "ok", "message": f"已移除 {old_email}"})

                # --- Phase 2: 邀请新成员 ---
                step_offset[0] = 100
                on_step_replace({"type": "step", "name": "--- 阶段2: 邀请新成员 ---", "status": "info", "message": new_email})
                task = asyncio.ensure_future(
                    run_send_family_invite(profile_id, new_email, on_step=on_step_replace)
                )
                await _drain_queue(task, msg_queue)

                invite_result = task.result() if not task.exception() else None
                if not invite_result or not invite_result.success:
                    err_msg = f"已移除旧成员, 但邀请新成员失败: {invite_result.message if invite_result else str(task.exception())}"
                    await ws.send_json({"type": "result", "success": False, "message": err_msg, "duration_ms": 0})
                    continue

                await ws.send_json({"type": "step", "name": "邀请新成员完成", "status": "ok", "message": f"已邀请 {new_email}"})

                # --- Phase 3: 检查新成员是否在系统中有完整信息, 自动接受邀请 ---
                db3 = SessionLocal()
                try:
                    new_account = db3.query(Account).filter(Account.email == new_email).first()
                    new_profile = None
                    if new_account:
                        new_profile = db3.query(BrowserProfile).filter(BrowserProfile.account_id == new_account.id).first()
                    new_pwd = _decrypt(new_account.password) if new_account else ""
                    new_totp = _decrypt(new_account.totp_secret) if new_account else ""
                    new_email_db = new_account.email if new_account else ""
                finally:
                    db3.close()

                if not new_account or not new_pwd:
                    # 新成员不在系统中或没有完整信息, 到此结束
                    await ws.send_json({"type": "step", "name": "自动接受邀请", "status": "skip", "message": f"{new_email} 不在系统中或信息不完整, 仅完成邀请"})
                    await ws.send_json({"type": "result", "success": True, "message": f"替换完成: 已移除 {old_email}, 已邀请 {new_email} (需手动接受)", "duration_ms": 0})
                    continue

                # 新成员在系统中, 尝试自动接受邀请
                step_offset[0] = 200
                on_step_replace({"type": "step", "name": "--- 阶段3: 新成员自动接受邀请 ---", "status": "info", "message": f"{new_email} 在系统中, 将自动接受"})

                # 检查新成员浏览器是否已启动
                need_auto_login = False
                if not new_profile or not browser_manager.is_running(new_profile.id):
                    # 需要先启动浏览器并登录
                    on_step_replace({"type": "step", "name": "启动新成员浏览器", "status": "running", "message": new_email})
                    try:
                        if not new_profile:
                            await ws.send_json({"type": "step", "name": "自动接受邀请", "status": "skip", "message": f"{new_email} 没有浏览器配置, 仅完成邀请"})
                            await ws.send_json({"type": "result", "success": True, "message": f"替换完成: 已移除 {old_email}, 已邀请 {new_email} (需手动接受)", "duration_ms": 0})
                            continue
                        # 重新查询 new_profile 确保 ORM 关系完整 (account 关联)
                        db4 = SessionLocal()
                        try:
                            from sqlalchemy.orm import joinedload
                            fresh_profile = db4.query(BrowserProfile).options(joinedload(BrowserProfile.account)).get(new_profile.id)
                            # 触发加载以确保 detach 后仍可访问
                            _ = fresh_profile.account
                        finally:
                            db4.close()
                        await browser_manager.launch(fresh_profile)
                        on_step_replace({"type": "step", "name": "启动新成员浏览器", "status": "ok", "message": "浏览器已启动"})
                        need_auto_login = True
                    except Exception as e:
                        on_step_replace({"type": "step", "name": "启动新成员浏览器", "status": "fail", "message": str(e)})
                        await _drain_queue(asyncio.ensure_future(asyncio.sleep(0)), msg_queue)
                        await ws.send_json({"type": "result", "success": True, "message": f"替换部分完成: 已移除 {old_email}, 已邀请 {new_email}, 但启动新成员浏览器失败", "duration_ms": 0})
                        continue

                    await _drain_queue(asyncio.ensure_future(asyncio.sleep(0)), msg_queue)

                # 如果需要先登录
                if need_auto_login:
                    step_offset[0] = 300
                    on_step_replace({"type": "step", "name": "--- 新成员自动登录 ---", "status": "info", "message": new_email})
                    # 获取新成员的验证链接和辅助邮箱
                    new_verify_url = ""
                    new_recovery_email = ""
                    if new_account:
                        from services.verification import extract_verification_link
                        new_verify_url = extract_verification_link(new_account.notes or "") or ""
                        new_recovery_email = _decrypt(new_account.recovery_email) or ""
                    task = asyncio.ensure_future(
                        run_auto_login(new_profile.id, new_email_db, new_pwd, new_totp, new_recovery_email, new_verify_url, on_step=on_step_replace)
                    )
                    await _drain_queue(task, msg_queue)

                    login_result = task.result() if not task.exception() else None
                    if not login_result or not login_result.success:
                        err_msg = f"新成员登录失败: {login_result.message if login_result else str(task.exception())}"
                        await ws.send_json({"type": "result", "success": True, "message": f"替换部分完成: 已移除 {old_email}, 已邀请 {new_email}, 但新成员登录失败", "duration_ms": 0})
                        continue

                # 接受邀请
                step_offset[0] = 400
                on_step_replace({"type": "step", "name": "--- 新成员接受邀请 ---", "status": "info", "message": new_email})
                task = asyncio.ensure_future(
                    run_accept_family_invite(new_profile.id, on_step=on_step_replace)
                )
                await _drain_queue(task, msg_queue)

                accept_result = task.result() if not task.exception() else None
                if accept_result and accept_result.success:
                    _sync_group_after_action("family-accept", new_account.id, True, accept_result.message, {"manager_account_id": account_id})
                    await ws.send_json({"type": "result", "success": True, "message": f"替换成功: 已移除 {old_email}, 已邀请并接受 {new_email}", "duration_ms": 0})
                else:
                    err = accept_result.message if accept_result else str(task.exception())
                    await ws.send_json({"type": "result", "success": True, "message": f"替换部分完成: 已移除 {old_email}, 已邀请 {new_email}, 但接受邀请失败: {err}", "duration_ms": 0})

                # 关闭新成员浏览器 (如果是本次临时启动的)
                if need_auto_login:
                    try:
                        await browser_manager.stop(new_profile.id)
                        on_step_replace({"type": "step", "name": "关闭新成员浏览器", "status": "ok", "message": "已关闭"})
                        await _drain_queue(asyncio.ensure_future(asyncio.sleep(0)), msg_queue)
                    except Exception:
                        pass
                continue
            else:
                await ws.send_json({"type": "error", "message": f"未知操作: {action}"})
                continue

            # 实时转发步骤消息，直到任务完成
            while not task.done():
                try:
                    msg = msg_queue.get_nowait()
                    await ws.send_json(msg)
                except queue.Empty:
                    await asyncio.sleep(0.1)

            # 发送队列中剩余消息
            while not msg_queue.empty():
                msg = msg_queue.get_nowait()
                await ws.send_json(msg)

            # 检查任务异常
            if task.exception():
                await ws.send_json({
                    "type": "result",
                    "success": False,
                    "message": f"操作异常: {task.exception()}",
                    "duration_ms": 0,
                })
            else:
                # 操作完成后自动同步分组
                result = task.result()
                if result and result.success:
                    _save_cookies(account_id, profile_id)
                    # OAuth 成功后保存凭证
                    if action == "oauth" and hasattr(result, 'extra') and result.extra and result.extra.get("credential"):
                        _save_oauth_credential(account_id, result.extra["credential"])
                if result and action in ("family-create", "family-accept", "family-remove", "family-leave"):
                    extra_data = {}
                    if action == "family-remove":
                        extra_data["member_email"] = data.get("member_email", "")
                    elif action == "family-accept":
                        extra_data["manager_account_id"] = data.get("manager_account_id")
                    _sync_group_after_action(
                        action=action,
                        account_id=account_id,
                        success=result.success,
                        result_msg=result.message,
                        extra=extra_data,
                    )

    except WebSocketDisconnect:
        logger.info("WebSocket automation client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await ws.close(code=1011)
        except Exception:
            pass
