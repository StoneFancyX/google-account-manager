"""Google 账号自动化操作服务

基于 DrissionPage + httpx RPC 实现:
- DrissionPage: 登录、密码重验证 (获取 rapt)
- httpx (FamilyAPI): 家庭组所有 RPC 操作
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Callable

from services.browser import browser_manager, login_sync, get_rapt_sync
from services.family_api import FamilyAPI, NoInvitationError, TokenError, RPCError

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / ".automation_logs"


# ============================================================
# 调试模式
# ============================================================

def _is_debug_mode() -> bool:
    try:
        from models.database import SessionLocal
        from models.orm import Config
        db = SessionLocal()
        try:
            row = db.query(Config).filter(Config.key == "debug_mode").first()
            return row.value == "true" if row else False
        finally:
            db.close()
    except Exception:
        return False


# ============================================================
# 步骤记录器 (简化版, 无截图)
# ============================================================

@dataclass
class StepLog:
    step_num: int
    name: str
    status: str  # "ok" / "fail" / "skip" / "info"
    message: str
    timestamp: str
    duration_ms: int = 0

    def to_dict(self):
        d = {
            "step": self.step_num,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.duration_ms:
            d["duration_ms"] = self.duration_ms
        return d


class StepTracker:
    """自动化步骤追踪器 (RPC 版, 无截图)"""

    def __init__(self, task_name: str, on_step: Callable = None):
        self.task_name = task_name
        self.on_step = on_step
        self.steps: List[StepLog] = []
        self._step_counter = 0
        self._start_time = time.time()
        self._step_start = 0.0

    def step(self, name: str, status: str, message: str = ""):
        self._step_counter += 1
        now = datetime.now(timezone.utc).isoformat()
        duration = int((time.time() - self._step_start) * 1000) if self._step_start else 0
        self._step_start = time.time()

        log = StepLog(
            step_num=self._step_counter,
            name=name,
            status=status,
            message=message,
            timestamp=now,
            duration_ms=duration,
        )
        self.steps.append(log)

        icon = {"ok": "✓", "fail": "✗", "skip": "⊘", "info": "ℹ"}.get(status, "?")
        logger.info(f"[{self.task_name}] {icon} Step {self._step_counter}: {name} - {message}")

        if self.on_step:
            try:
                data = log.to_dict()
                data["type"] = "step"
                data["status"] = "running" if status == "info" else status
                self.on_step(data)
            except Exception:
                pass

    def result(self, success: bool, message: str, step: str = "done") -> "AutomationResult":
        total_ms = int((time.time() - self._start_time) * 1000)
        logger.info(f"[{self.task_name}] {'[OK]' if success else '[FAIL]'} {message} ({total_ms}ms)")

        res = AutomationResult(
            success=success,
            message=message,
            step=step,
            steps=[s.to_dict() for s in self.steps],
            duration_ms=total_ms,
        )

        if self.on_step:
            try:
                self.on_step({
                    "type": "result",
                    "success": success,
                    "message": message,
                    "step": step,
                    "duration_ms": total_ms,
                })
            except Exception:
                pass

        return res


@dataclass
class AutomationResult:
    success: bool
    message: str
    step: str = ""
    steps: list = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self):
        return {
            "success": self.success,
            "message": self.message,
            "step": self.step,
            "steps": self.steps,
            "duration_ms": self.duration_ms,
        }


# ============================================================
# 同步操作函数
# ============================================================

def auto_login_sync(page, email: str, password: str, totp_secret: str = "",
                    recovery_email: str = "", verification_url: str = "",
                    on_step=None) -> AutomationResult:
    """自动登录 Google 账号"""
    tracker = StepTracker("login", on_step)

    tracker.step("打开登录页", "info", "accounts.google.com")
    ok = login_sync(page, email, password, totp_secret, recovery_email)

    if ok:
        return tracker.result(True, f"登录成功: {email}")
    else:
        return tracker.result(False, f"登录失败: {email}", step="login")


def create_family_group_sync(page, on_step=None) -> AutomationResult:
    """创建家庭组 (纯 RPC)"""
    tracker = StepTracker("create_family", on_step)

    tracker.step("提取 cookies", "info")
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            tracker.step("查询家庭组状态", "info")
            status = api.query_status()
            if status["has_family"]:
                return tracker.result(False, "已有家庭组, 无需创建", step="check")

            tracker.step("创建家庭组", "info", "nKULBd → Wffnob → c5gch")
            ok = api.create_family()

            if ok:
                return tracker.result(True, "家庭组创建成功")
            else:
                return tracker.result(False, "家庭组创建失败", step="create")
    except (TokenError, RPCError) as e:
        return tracker.result(False, str(e), step="rpc")
    except Exception as e:
        return tracker.result(False, f"异常: {e}", step="error")


def send_family_invite_sync(page, invite_email: str, on_step=None) -> AutomationResult:
    """发送家庭组邀请 (纯 RPC)"""
    tracker = StepTracker("send_invite", on_step)

    tracker.step("提取 cookies", "info")
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            tracker.step("发送邀请", "info", invite_email)
            result = api.send_invite(invite_email)

            if result["success"]:
                return tracker.result(True, f"邀请已发送: {invite_email}")
            else:
                return tracker.result(False, f"邀请发送失败: {invite_email}", step="invite")
    except (TokenError, RPCError) as e:
        return tracker.result(False, str(e), step="rpc")
    except Exception as e:
        return tracker.result(False, f"异常: {e}", step="error")


def accept_family_invite_sync(page, on_step=None) -> AutomationResult:
    """接受家庭组邀请 (纯 RPC)"""
    tracker = StepTracker("accept_invite", on_step)

    tracker.step("提取 cookies", "info")
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            tracker.step("查找并接受邀请", "info")
            result = api.accept_invite()

            if result["success"]:
                return tracker.result(True, "邀请已接受")
            else:
                return tracker.result(False, "接受邀请失败", step="accept")
    except NoInvitationError:
        return tracker.result(False, "没有待接受的邀请", step="no_invite")
    except (TokenError, RPCError) as e:
        return tracker.result(False, str(e), step="rpc")
    except Exception as e:
        return tracker.result(False, f"异常: {e}", step="error")


def remove_family_member_sync(page, member_email: str, password: str = "",
                              totp_secret: str = "", on_step=None) -> AutomationResult:
    """移除家庭组成员 (需要 rapt)"""
    tracker = StepTracker("remove_member", on_step)

    tracker.step("提取 cookies", "info")
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            # 先查成员列表, 找到 user_id
            tracker.step("查询成员列表", "info")
            members_info = api.query_members()
            if not members_info["has_family"]:
                return tracker.result(False, "不在家庭组中", step="check")

            target = None
            for m in members_info["members"]:
                if m.get("email", "").lower() == member_email.lower():
                    target = m
                    break

            if not target:
                return tracker.result(False, f"未找到成员: {member_email}", step="find_member")

            member_user_id = target["user_id"]
            tracker.step("找到成员", "ok", f"{target['name']} ({member_user_id})")

            # 获取 rapt
            tracker.step("密码重验证", "info", "获取 rapt token")
            rapt = get_rapt_sync(page, f"/family/remove/g/{member_user_id}", password, totp_secret)
            if not rapt:
                return tracker.result(False, "获取 rapt token 失败", step="rapt")
            tracker.step("rapt 获取成功", "ok")

            # 刷新 cookies (重验证后 cookies 可能更新)
            cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))
            api.client.cookies.update(cookies)
            api.refresh_tokens()

            # 执行移除
            tracker.step("移除成员", "info", member_email)
            ok = api.remove_member(member_user_id, rapt)

            if ok:
                return tracker.result(True, f"已移除成员: {member_email}")
            else:
                return tracker.result(False, f"移除成员失败: {member_email}", step="remove")
    except (TokenError, RPCError) as e:
        return tracker.result(False, str(e), step="rpc")
    except Exception as e:
        return tracker.result(False, f"异常: {e}", step="error")


def leave_family_group_sync(page, password: str = "", totp_secret: str = "",
                            on_step=None) -> AutomationResult:
    """退出/删除家庭组 (需要 rapt)"""
    tracker = StepTracker("leave_family", on_step)

    tracker.step("提取 cookies", "info")
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            tracker.step("查询家庭组状态", "info")
            members_info = api.query_members()
            if not members_info["has_family"]:
                return tracker.result(False, "不在家庭组中", step="check")

            is_admin = members_info["is_admin"]
            action = "删除家庭组" if is_admin else "退出家庭组"
            target_path = "/family/delete" if is_admin else "/family/leave"

            # 获取 rapt
            tracker.step("密码重验证", "info", f"{action} - 获取 rapt")
            rapt = get_rapt_sync(page, target_path, password, totp_secret)
            if not rapt:
                return tracker.result(False, "获取 rapt token 失败", step="rapt")
            tracker.step("rapt 获取成功", "ok")

            # 刷新 cookies
            cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))
            api.client.cookies.update(cookies)
            api.refresh_tokens()

            # 执行
            tracker.step(action, "info")
            if is_admin:
                ok = api.delete_family(rapt)
            else:
                ok = api.leave_family(rapt)

            if ok:
                return tracker.result(True, f"{action}成功")
            else:
                return tracker.result(False, f"{action}失败", step="leave_delete")
    except (TokenError, RPCError) as e:
        return tracker.result(False, str(e), step="rpc")
    except Exception as e:
        return tracker.result(False, f"异常: {e}", step="error")


# ============================================================
# 家庭组发现 (纯 RPC)
# ============================================================

@dataclass
class FamilyDiscoverResult:
    success: bool
    has_group: bool = False
    role: str = ""
    members: list = field(default_factory=list)
    member_count: int = 0
    message: str = ""
    cookies_expired: bool = False  # cookies 是否已过期

    def to_dict(self):
        d = {
            "success": self.success,
            "has_group": self.has_group,
            "role": self.role,
            "members": self.members,
            "member_count": self.member_count,
            "message": self.message,
        }
        if self.cookies_expired:
            d["cookies_expired"] = True
        return d


def discover_family_group_sync(page, on_step=None) -> FamilyDiscoverResult:
    """发现家庭组关系 (纯 RPC)"""
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            members_info = api.query_members()

            if not members_info["has_family"]:
                return FamilyDiscoverResult(success=True, has_group=False, message="无家庭组")

            role = "manager" if members_info["is_admin"] else "member"
            members = []
            for m in members_info["members"]:
                if m.get("pending"):
                    role_str = "pending"
                elif m["role"] == 1:
                    role_str = "manager"
                else:
                    role_str = "member"
                members.append({
                    "name": m["name"],
                    "email": m.get("email", ""),
                    "role": role_str,
                })

            return FamilyDiscoverResult(
                success=True,
                has_group=True,
                role=role,
                members=members,
                member_count=members_info["member_count"],
                message=f"家庭组: {role}, {members_info['member_count']} 成员",
            )
    except Exception as e:
        return FamilyDiscoverResult(success=False, message=str(e))


def _discover_from_cookies(cookies: dict) -> FamilyDiscoverResult:
    """纯 cookies 发现家庭组 (不需要浏览器)"""
    try:
        with FamilyAPI(cookies) as api:
            members_info = api.query_members()

            if not members_info["has_family"]:
                return FamilyDiscoverResult(success=True, has_group=False, message="无家庭组")

            role = "manager" if members_info["is_admin"] else "member"
            members = []
            for m in members_info["members"]:
                if m.get("pending"):
                    role_str = "pending"
                elif m["role"] == 1:
                    role_str = "manager"
                else:
                    role_str = "member"
                members.append({
                    "name": m["name"],
                    "email": m.get("email", ""),
                    "role": role_str,
                })

            return FamilyDiscoverResult(
                success=True,
                has_group=True,
                role=role,
                members=members,
                member_count=members_info["member_count"],
                message=f"家庭组: {role}, {members_info['member_count']} 成员",
            )
    except TokenError:
        return FamilyDiscoverResult(
            success=False,
            message="Cookies 已过期，请重新登录账号",
            cookies_expired=True,
        )
    except Exception as e:
        error_msg = str(e)
        # 常见的 cookies 过期表现
        if any(kw in error_msg.lower() for kw in ("401", "403", "redirect", "login", "sign in")):
            return FamilyDiscoverResult(
                success=False,
                message="Cookies 已过期，请重新登录账号",
                cookies_expired=True,
            )
        return FamilyDiscoverResult(success=False, message=f"查询失败: {error_msg}")


def discover_family_by_cookies(
    account_id: int,
    saved_cookies_json: str,
    browser_profile_id: int = None,
) -> FamilyDiscoverResult:
    """智能发现家庭组: 保存的 cookies → 浏览器 cookies → 报错

    优先级:
      1. 用数据库保存的 cookies 直接查询 (不需要浏览器)
      2. 保存的 cookies 为空或已过期, 且浏览器在运行 → 从浏览器获取 cookies 重试 + 更新数据库
      3. 都失败 → 返回提示 "需要重新登录"
    """
    import json as _json

    # 1. 尝试用保存的 cookies
    cookies = {}
    if saved_cookies_json:
        try:
            cookies = _json.loads(saved_cookies_json)
        except (ValueError, TypeError):
            pass

    if cookies:
        result = _discover_from_cookies(cookies)
        if result.success:
            return result
        if not result.cookies_expired:
            return result
        # cookies 过期, 继续尝试浏览器刷新
        logger.info(f"[discover] account #{account_id} 保存的 cookies 已过期, 尝试浏览器刷新")
    else:
        logger.info(f"[discover] account #{account_id} 没有保存的 cookies, 尝试从浏览器获取")

    # 2. 尝试从运行中的浏览器获取新 cookies (无论是空 cookies 还是过期 cookies 都走这里)
    if browser_profile_id and browser_manager.is_running(browser_profile_id):
        fresh_cookies = browser_manager.get_cookies(browser_profile_id)
        if fresh_cookies:
            logger.info(f"[discover] 从浏览器获取到 {len(fresh_cookies)} 个 cookies")
            result = _discover_from_cookies(fresh_cookies)
            if result.success:
                # 更新数据库中的 cookies
                try:
                    from models.database import SessionLocal
                    from models.orm import Account
                    db = SessionLocal()
                    try:
                        acc = db.query(Account).get(account_id)
                        if acc:
                            acc.cookies_json = _json.dumps(fresh_cookies)
                            acc.updated_at = datetime.now(timezone.utc)
                            db.commit()
                            logger.info(f"[discover] 从浏览器刷新 cookies 成功, 已更新 account #{account_id}")
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"[discover] 更新 cookies 失败: {e}")
                return result
            # 浏览器 cookies 也不行
            return result
        else:
            logger.warning(f"[discover] 浏览器在运行但获取 cookies 为空")
    else:
        logger.info(f"[discover] account #{account_id} 浏览器未运行 (profile_id={browser_profile_id})")

    # 3. 没有可用的 cookies
    return FamilyDiscoverResult(
        success=False,
        message="未找到可用的登录信息，请先登录账号" if not cookies else "Cookies 已过期，请重新登录账号刷新",
        cookies_expired=True,
    )


# ============================================================
# 工具函数
# ============================================================

def _get_profile_id_from_page(page) -> int:
    """从 page 对象反查 profile_id"""
    for pid, inst in browser_manager._instances.items():
        if inst.page is page:
            return pid
    # 如果找不到, 返回第一个运行中的
    ids = browser_manager.get_running_ids()
    return ids[0] if ids else 0


# ============================================================
# 异步包装器
# ============================================================

async def run_auto_login(profile_id: int, email: str, password: str,
                         totp_secret: str = "", recovery_email: str = "",
                         verification_url: str = "", on_step=None) -> AutomationResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, auto_login_sync, page, email, password, totp_secret,
        recovery_email, verification_url, on_step
    )


async def run_create_family_group(profile_id: int, on_step=None) -> AutomationResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, create_family_group_sync, page, on_step)


async def run_send_family_invite(profile_id: int, invite_email: str,
                                 on_step=None) -> AutomationResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, send_family_invite_sync, page, invite_email, on_step
    )


async def run_accept_family_invite(profile_id: int, on_step=None) -> AutomationResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, accept_family_invite_sync, page, on_step)


async def run_remove_family_member(profile_id: int, member_email: str,
                                   password: str = "", totp_secret: str = "",
                                   on_step=None) -> AutomationResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, remove_family_member_sync, page, member_email, password, totp_secret, on_step
    )


async def run_leave_family_group(profile_id: int, password: str = "",
                                 totp_secret: str = "", on_step=None) -> AutomationResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, leave_family_group_sync, page, password, totp_secret, on_step
    )


async def run_discover_family_group(profile_id: int, on_step=None) -> FamilyDiscoverResult:
    page = browser_manager.get_page(profile_id)
    if not page:
        return FamilyDiscoverResult(success=False, message="浏览器未启动")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, discover_family_group_sync, page, on_step)
