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

    def result(self, success: bool, message: str, step: str = "done", extra: dict = None) -> "AutomationResult":
        total_ms = int((time.time() - self._start_time) * 1000)
        logger.info(f"[{self.task_name}] {'[OK]' if success else '[FAIL]'} {message} ({total_ms}ms)")

        res = AutomationResult(
            success=success,
            message=message,
            step=step,
            steps=[s.to_dict() for s in self.steps],
            duration_ms=total_ms,
            extra=extra or {},
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
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        d = {
            "success": self.success,
            "message": self.message,
            "step": self.step,
            "steps": self.steps,
            "duration_ms": self.duration_ms,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


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
                error = result.get("error", "接受邀请失败")
                return tracker.result(False, error, step="accept")
    except NoInvitationError:
        return tracker.result(False, "没有待接受的邀请", step="no_invite")
    except (TokenError, RPCError) as e:
        return tracker.result(False, str(e), step="rpc")
    except Exception as e:
        return tracker.result(False, f"异常: {e}", step="error")


def remove_family_member_sync(page, member_email: str, password: str = "",
                              totp_secret: str = "", on_step=None) -> AutomationResult:
    """移除家庭组成员 (已接受成员需要 rapt, 未接受成员撤销邀请)"""
    tracker = StepTracker("remove_member", on_step)

    tracker.step("提取 cookies", "info")
    cookies = browser_manager.get_cookies(_get_profile_id_from_page(page))

    try:
        with FamilyAPI(cookies) as api:
            # 先查成员列表, 找到目标
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

            tracker.step("找到成员", "ok", f"{target['name']} ({target['user_id']})")

            # pending 成员: 撤销邀请 (不需要 rapt)
            if target.get("pending"):
                invitation_id = target.get("invitation_id")
                if not invitation_id:
                    return tracker.result(False, f"未找到邀请 ID: {member_email}", step="no_invite_id")

                tracker.step("撤销邀请", "info", member_email)
                ok = api.cancel_invite(invitation_id)
                if ok:
                    return tracker.result(True, f"已撤销邀请: {member_email}")
                else:
                    return tracker.result(False, f"撤销邀请失败: {member_email}", step="cancel")

            # 已接受成员: 需要 rapt 移除
            member_user_id = target["user_id"]

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
    subscription_status: str = ""  # 订阅状态: free / ultra
    subscription_expiry: str = ""  # 订阅到期日, 如 "2026年3月23日"
    country: str = ""  # 账号所属国家/地区 (英文)
    country_cn: str = ""  # 中文国家名

    def to_dict(self):
        d = {
            "success": self.success,
            "has_group": self.has_group,
            "role": self.role,
            "members": self.members,
            "member_count": self.member_count,
            "message": self.message,
            "subscription_status": self.subscription_status,
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
    """纯 cookies 发现家庭组 + 查询订阅状态 + 查询地区 (不需要浏览器)"""
    try:
        with FamilyAPI(cookies) as api:
            members_info = api.query_members()

            # 查询订阅状态 (无论是否有家庭组都查)
            sub_status = ""
            sub_expiry = ""
            try:
                sub_info = api.query_subscription()
                sub_status = sub_info.get("status", "free")
                sub_expiry = sub_info.get("renew_date", "")
            except Exception as e:
                logger.warning(f"[discover] 查询订阅状态失败: {e}")

            # 查询账号地区
            country = ""
            country_cn = ""
            try:
                country_info = api.query_country()
                country = country_info.get("country", "")
                country_cn = country_info.get("country_cn", "")
            except Exception as e:
                logger.warning(f"[discover] 查询地区失败: {e}")

            if not members_info["has_family"]:
                return FamilyDiscoverResult(
                    success=True, has_group=False, message="无家庭组",
                    subscription_status=sub_status,
                    subscription_expiry=sub_expiry,
                    country=country,
                    country_cn=country_cn,
                )

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
                subscription_status=sub_status,
                subscription_expiry=sub_expiry,
                country=country,
                country_cn=country_cn,
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


def _save_cookies_to_db(account_id: int, cookies: dict):
    """保存 cookies 到数据库"""
    import json as _json
    try:
        from models.database import SessionLocal
        from models.orm import Account
        db = SessionLocal()
        try:
            acc = db.query(Account).get(account_id)
            if acc:
                acc.cookies_json = _json.dumps(cookies)
                acc.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[discover] cookies 已更新 → account #{account_id}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[discover] 更新 cookies 失败: {e}")


def _auto_login_and_get_cookies(
    browser_profile_id: int,
    email: str,
    password: str,
    totp_secret: str = "",
    recovery_email: str = "",
) -> Optional[dict]:
    """自动启动浏览器 → 登录 → 获取 cookies → 关闭浏览器

    注意: 强制关闭 headless 模式, 因为 Google 会检测并拦截 headless 登录。

    Returns: cookies dict if success, None if failed
    """
    import asyncio as _aio

    # 如果浏览器已在运行, 直接登录获取 cookies
    already_running = browser_manager.is_running(browser_profile_id)

    if not already_running:
        # 启动浏览器 (强制 headless=False, Google 登录不支持无头模式)
        try:
            from models.database import SessionLocal
            from models.orm import BrowserProfile
            db = SessionLocal()
            try:
                profile = db.query(BrowserProfile).get(browser_profile_id)
                if not profile:
                    logger.warning(f"[auto-login] 找不到浏览器配置 profile_id={browser_profile_id}")
                    return None
            finally:
                db.close()

            # 同步环境中启动浏览器 (launch 是 async 方法)
            loop = None
            try:
                loop = _aio.get_event_loop()
            except RuntimeError:
                loop = _aio.new_event_loop()
                _aio.set_event_loop(loop)

            if loop.is_running():
                # 在运行中的 event loop 里, 用线程启动
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(lambda: _aio.run(browser_manager.launch(profile, headless=False)))
                    future.result(timeout=30)
            else:
                loop.run_until_complete(browser_manager.launch(profile, headless=False))

            logger.info(f"[auto-login] 浏览器已启动 profile_id={browser_profile_id}")
        except Exception as e:
            logger.error(f"[auto-login] 启动浏览器失败: {e}")
            return None

    # 登录
    page = browser_manager.get_page(browser_profile_id)
    if not page:
        logger.error(f"[auto-login] 获取 page 失败 profile_id={browser_profile_id}")
        return None

    try:
        ok = login_sync(page, email, password, totp_secret, recovery_email)
        if not ok:
            logger.warning(f"[auto-login] 登录失败 email={email}")
            return None

        logger.info(f"[auto-login] 登录成功 email={email}")
        cookies = browser_manager.get_cookies(browser_profile_id)
        if not cookies:
            logger.warning(f"[auto-login] 登录成功但获取 cookies 为空")
            return None

        logger.info(f"[auto-login] 获取到 {len(cookies)} 个 cookies")
        return cookies
    except Exception as e:
        logger.error(f"[auto-login] 登录异常: {e}")
        return None
    finally:
        # 如果是我们启动的浏览器, 关闭它
        if not already_running:
            try:
                if browser_manager.is_running(browser_profile_id):
                    loop = None
                    try:
                        loop = _aio.get_event_loop()
                    except RuntimeError:
                        loop = _aio.new_event_loop()
                        _aio.set_event_loop(loop)

                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(lambda: _aio.run(browser_manager.stop(browser_profile_id)))
                            future.result(timeout=15)
                    else:
                        loop.run_until_complete(browser_manager.stop(browser_profile_id))
                    logger.info(f"[auto-login] 浏览器已关闭 profile_id={browser_profile_id}")
            except Exception as e:
                logger.warning(f"[auto-login] 关闭浏览器失败: {e}")


def discover_family_by_cookies(
    account_id: int,
    saved_cookies_json: str,
    browser_profile_id: int = None,
    email: str = "",
    password: str = "",
    totp_secret: str = "",
    recovery_email: str = "",
) -> FamilyDiscoverResult:
    """智能发现家庭组: 保存的 cookies → 浏览器 cookies → 自动登录刷新 → 报错

    优先级:
      1. 用数据库保存的 cookies 直接查询 (不需要浏览器)
      2. 保存的 cookies 为空或已过期, 且浏览器在运行 → 从浏览器获取 cookies 重试
      3. 自动启动浏览器 → 登录 → 获取新 cookies → 重新查询
      4. 都失败 → 返回提示 "需要重新登录"
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
        logger.info(f"[discover] account #{account_id} 保存的 cookies 已过期, 尝试刷新")
    else:
        logger.info(f"[discover] account #{account_id} 没有保存的 cookies, 尝试获取")

    # 2. 尝试从运行中的浏览器获取新 cookies
    if browser_profile_id and browser_manager.is_running(browser_profile_id):
        fresh_cookies = browser_manager.get_cookies(browser_profile_id)
        if fresh_cookies:
            logger.info(f"[discover] 从运行中的浏览器获取到 {len(fresh_cookies)} 个 cookies")
            result = _discover_from_cookies(fresh_cookies)
            if result.success:
                _save_cookies_to_db(account_id, fresh_cookies)
                return result
            # 浏览器里的 cookies 也过期了 → 需要重新登录
            if not result.cookies_expired:
                return result
            logger.info(f"[discover] 浏览器 cookies 也已过期, 尝试自动登录")

    # 3. 自动登录刷新 cookies (需要账号凭证)
    if browser_profile_id and email and password:
        logger.info(f"[discover] account #{account_id} 尝试自动登录获取新 cookies")
        fresh_cookies = _auto_login_and_get_cookies(
            browser_profile_id, email, password, totp_secret, recovery_email
        )
        if fresh_cookies:
            result = _discover_from_cookies(fresh_cookies)
            if result.success:
                _save_cookies_to_db(account_id, fresh_cookies)
                return result
            return result
        else:
            return FamilyDiscoverResult(
                success=False,
                message="自动登录失败，无法获取最新 cookies",
                cookies_expired=True,
            )

    # 4. 没有可用的 cookies，也没有凭证自动登录
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


async def run_oauth(profile_id: int, on_step=None, password: str = "", totp_secret: str = "") -> AutomationResult:
    """在已登录浏览器中自动完成 OAuth 授权"""
    page = browser_manager.get_page(profile_id)
    if not page:
        return AutomationResult(success=False, message="浏览器未启动", step="init")
    from services.oauth import oauth_sync
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, oauth_sync, page, on_step, password, totp_secret
    )
