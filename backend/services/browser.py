"""浏览器管理服务 - 使用 DrissionPage 实现登录与 rapt 获取

职责:
  1. 管理浏览器实例生命周期 (启动/停止)
  2. 登录 Google 账号 → 提取 cookies
  3. 导航到敏感页面 → 密码/TOTP 重验证 → 获取 rapt token
"""

import json
import logging
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pyotp
from DrissionPage import WebPage, ChromiumOptions

logger = logging.getLogger(__name__)

# 浏览器用户数据根目录
PROFILES_DIR = Path(__file__).resolve().parent.parent / ".browser_profiles"


@dataclass
class BrowserInstance:
    """运行中的浏览器实例"""
    profile_id: int
    page: object = field(default=None, repr=False)
    data_dir: str = ""
    cookies: dict = field(default_factory=dict)


class BrowserManager:
    """管理所有 DrissionPage 浏览器实例"""

    def __init__(self):
        self._instances: Dict[int, BrowserInstance] = {}
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_data_dir(profile_id: int, account_email: str = "") -> Path:
        """获取 profile 对应的 user-data-dir"""
        mapping_file = PROFILES_DIR / ".mapping.json"
        mapping = {}
        if mapping_file.exists():
            try:
                mapping = json.loads(mapping_file.read_text())
            except Exception:
                mapping = {}

        key = str(profile_id)
        need_new = key not in mapping

        # 已有 mapping 但账号不匹配时，说明 profile 被重新关联了，需要新建目录
        if not need_new and account_email:
            email_prefix = account_email.split("@")[0].lower()
            existing_dir = mapping[key].lower()
            if email_prefix not in existing_dir:
                logger.info(f"[browser] profile {profile_id} 账号已变更, 重新分配目录 ({mapping[key]} -> {account_email})")
                need_new = True

        if need_new:
            prefix = account_email.split("@")[0] if account_email else f"profile{profile_id}"
            prefix = "".join(c if c.isalnum() or c in "._-" else "_" for c in prefix)
            short_id = uuid.uuid4().hex[:8]
            mapping[key] = f"{prefix}_{short_id}"
            mapping_file.write_text(json.dumps(mapping, indent=2))

        data_dir = PROFILES_DIR / mapping[key]
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def is_running(self, profile_id: int) -> bool:
        return profile_id in self._instances

    def get_running_ids(self) -> List[int]:
        return list(self._instances.keys())

    @staticmethod
    def _is_headless_mode() -> bool:
        try:
            from models.database import SessionLocal
            from models.orm import Config
            db = SessionLocal()
            try:
                row = db.query(Config).filter(Config.key == "headless_mode").first()
                return row.value == "true" if row else False
            finally:
                db.close()
        except Exception:
            return False

    async def launch(self, profile, *, headless: Optional[bool] = None) -> BrowserInstance:
        """启动 DrissionPage 浏览器实例

        Args:
            profile: BrowserProfile ORM 对象或 profile_id
            headless: 强制指定无头模式, None 则读取数据库设置
        """
        from models.orm import BrowserProfile
        profile_id = profile.id if isinstance(profile, BrowserProfile) else profile
        account_email = ""
        if hasattr(profile, "account") and profile.account:
            account_email = profile.account.email

        if self.is_running(profile_id):
            raise RuntimeError(f"Profile {profile_id} 已在运行中")

        data_dir = self._get_data_dir(profile_id, account_email)
        use_headless = headless if headless is not None else self._is_headless_mode()

        co = ChromiumOptions()
        # 每个实例使用独立随机端口，避免接管已有浏览器
        import random
        port = random.randint(9600, 59600)
        co.set_address(f"127.0.0.1:{port}")
        co.set_argument("--lang", "en-US")
        co.set_user_data_path(str(data_dir))
        if use_headless:
            co.headless()

        # 代理
        if hasattr(profile, "proxy_type") and profile.proxy_type and profile.proxy_host:
            proxy_url = f"{profile.proxy_type}://{profile.proxy_host}:{profile.proxy_port}"
            co.set_argument(f"--proxy-server={proxy_url}")

        page = WebPage(chromium_options=co)

        instance = BrowserInstance(
            profile_id=profile_id,
            page=page,
            data_dir=str(data_dir),
        )
        self._instances[profile_id] = instance
        logger.info(f"Browser launched: profile_id={profile_id}")
        return instance

    async def stop(self, profile_id: int) -> None:
        """停止浏览器实例"""
        instance = self._instances.pop(profile_id, None)
        if not instance:
            raise RuntimeError(f"Profile {profile_id} 未在运行")

        try:
            if instance.page:
                instance.page.quit()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

        logger.info(f"Browser stopped: profile_id={profile_id}")

    async def stop_all(self) -> None:
        for profile_id in list(self._instances.keys()):
            try:
                await self.stop(profile_id)
            except Exception as e:
                logger.warning(f"Error stopping profile {profile_id}: {e}")

    def get_status(self, profile_id: int) -> dict:
        if profile_id not in self._instances:
            return {"status": "stopped", "profile_id": profile_id}
        return {"status": "running", "profile_id": profile_id}

    def get_instance(self, profile_id: int) -> Optional[BrowserInstance]:
        return self._instances.get(profile_id)

    def get_page(self, profile_id: int):
        instance = self._instances.get(profile_id)
        return instance.page if instance else None

    def get_cookies(self, profile_id: int) -> dict[str, str]:
        """从浏览器实例提取 Google 域的 cookies

        优先使用 myaccount.google.com 域的 cookie 值 (FamilyAPI 需要),
        其次 accounts.google.com, 再次 .google.com。
        同名 cookie 高优先级域覆盖低优先级域。
        """
        instance = self._instances.get(profile_id)
        if not instance or not instance.page:
            return {}

        def _domain_priority(domain: str) -> int:
            if "myaccount.google" in domain:
                return 3
            if "accounts.google" in domain:
                return 2
            if domain.endswith(".google.com") or domain == ".google.com":
                return 1
            return 0

        cookies = {}
        priorities = {}
        for c in instance.page.cookies(all_domains=True):
            if isinstance(c, dict):
                name, value, domain = c.get("name", ""), c.get("value", ""), c.get("domain", "")
            else:
                name, value, domain = str(c.name), str(c.value), str(getattr(c, "domain", ""))

            if "google" not in domain:
                continue

            p = _domain_priority(domain)
            if p >= priorities.get(name, -1):
                cookies[name] = value
                priorities[name] = p

        return cookies

    async def run_in_browser_thread(self, profile_id: int, fn, *args):
        """DrissionPage 不需要线程隔离, 直接执行"""
        return fn(*args)

    def delete_profile_data(self, profile_id: int) -> None:
        """删除 profile 对应的浏览器数据目录"""
        if self.is_running(profile_id):
            raise RuntimeError(f"Profile {profile_id} 正在运行, 请先停止")

        mapping_file = PROFILES_DIR / ".mapping.json"
        mapping = {}
        if mapping_file.exists():
            try:
                mapping = json.loads(mapping_file.read_text())
            except Exception:
                mapping = {}

        key = str(profile_id)
        dir_name = mapping.get(key)
        if dir_name:
            data_dir = PROFILES_DIR / dir_name
            if data_dir.exists():
                shutil.rmtree(data_dir)
                logger.info(f"Profile data deleted: {data_dir}")
            del mapping[key]
            mapping_file.write_text(json.dumps(mapping, indent=2))


# 全局单例
browser_manager = BrowserManager()


# ── 登录与 rapt 获取 ─────────────────────────────────────


def login_sync(page, email: str, password: str, totp_secret: str = "",
               recovery_email: str = "") -> bool:
    """DrissionPage 同步登录 Google 账号

    Returns: True = 登录成功
    """
    # 先检测是否已登录 (user-data-dir 保留了上次会话)
    page.get("https://myaccount.google.com/")
    time.sleep(3)
    url = page.url
    # 已登录会停在 myaccount.google.com, 未登录会重定向到 google.com/account/about 或 accounts.google.com
    if "myaccount.google.com" in url and "account/about" not in url and "signin" not in url:
        # 确认是目标账号 (页面上应该有邮箱)
        page_text = page.html or ""
        if email.lower() in page_text.lower():
            logger.info(f"账号已登录 (session 有效), email={email}")
            return True
        else:
            logger.info(f"浏览器已登录其他账号, 继续登录 {email}")

    page.get("https://accounts.google.com/signin")
    time.sleep(2)

    # 已登录检测: 如果直接跳转到 myaccount 说明已登录
    if "myaccount.google.com" in page.url:
        logger.info(f"账号已登录 (跳转到 myaccount), email={email}")
        return True

    # 邮箱
    email_input = page.ele("#identifierId", timeout=10)
    if not email_input:
        use_another = page.ele("text:Use another account", timeout=3)
        if use_another:
            use_another.click()
            time.sleep(2)
            email_input = page.ele("#identifierId", timeout=10)
    if not email_input:
        logger.error(f"找不到邮箱输入框, URL: {page.url}")
        return False

    email_input.input(email)
    time.sleep(0.5)
    page.ele("#identifierNext", timeout=5).click()
    time.sleep(3)

    # 密码
    time.sleep(2)
    pwd_input = page.ele("@name=Passwd", timeout=15)
    if not pwd_input:
        logger.error("找不到密码输入框")
        return False
    pwd_input.input(password)
    time.sleep(0.5)
    page.ele("#passwordNext", timeout=5).click()
    time.sleep(3)

    # TOTP
    if "challenge" in page.url and totp_secret:
        code = pyotp.TOTP(totp_secret.replace(' ', '')).now()
        if "challenge/selection" in page.url:
            opt = page.ele("text:Authenticator", timeout=3)
            if opt:
                opt.click()
                time.sleep(2)
        totp_input = page.ele("#totpPin", timeout=10) or page.ele('input[type="tel"]', timeout=5)
        if totp_input:
            totp_input.input(code)
            time.sleep(0.5)
            btn = page.ele("#totpNext", timeout=5) or page.ele("text:Next", timeout=3)
            if btn:
                btn.click()
                time.sleep(3)

    time.sleep(2)

    # 处理登录后的中间页 (passkey 引导、恢复选项提示等)
    for _ in range(3):
        url = page.url
        if "speedbump" in url or "passkeyenrollment" in url or "signinoptions" in url:
            # 点击 "以后再说" / "Not now" / "Skip" 跳过
            skip_btn = (
                page.ele("text:以后再说", timeout=2)
                or page.ele("text:Not now", timeout=2)
                or page.ele("text:Skip", timeout=2)
                or page.ele("text:稍后再说", timeout=1)
            )
            if skip_btn:
                skip_btn.click()
                logger.info(f"跳过中间页: {url}")
                time.sleep(3)
                continue
        break

    # 登录成功判断: 多种成功后的 URL 模式
    url = page.url
    ok = (
        "myaccount" in url
        or "speedbump" in url  # passkey 引导页 (跳过按钮可能未点到, 但登录已完成)
        or "accounts.google.com/Default" in url
        or "accounts.google.com/" == url.rstrip("/") + "/"
        or ("signin" not in url and "challenge" not in url and "accounts.google.com" in url)
        or "google.com" in url and "signin" not in url and "challenge" not in url
    )
    # 额外检查: 如果页面上有头像/用户菜单, 说明已登录
    if not ok:
        avatar = page.ele("@aria-label=Google Account", timeout=2) or page.ele("img.gb_q", timeout=1)
        if avatar:
            ok = True
    logger.info(f"登录 {email}: {'OK' if ok else 'FAIL'}, URL: {url}")
    return ok


def handle_reauth_sync(page, password: str, totp_secret: str = "") -> Optional[str]:
    """处理密码+TOTP 重验证, 返回 rapt token

    Returns: rapt token string, or None if no reauth needed
    """
    if "challenge" not in page.url and "signin" not in page.url:
        # 检查 URL 中是否已有 rapt
        if "rapt=" in page.url:
            import re
            m = re.search(r'rapt=([^&]+)', page.url)
            return m.group(1) if m else None
        return None

    logger.info("密码重验证...")

    # 密码
    pwd_input = page.ele("@name=Passwd", timeout=5) or page.ele('input[type="password"]', timeout=5)
    if pwd_input:
        pwd_input.input(password)
        time.sleep(0.5)
        next_btn = page.ele("#passwordNext", timeout=3) or page.ele("text:Next", timeout=3)
        if next_btn:
            next_btn.click()
            time.sleep(3)

    # TOTP
    if "challenge" in page.url and totp_secret:
        code = pyotp.TOTP(totp_secret.replace(' ', '')).now()
        if "challenge/selection" in page.url:
            opt = page.ele("text:Authenticator", timeout=3)
            if opt:
                opt.click()
                time.sleep(2)
        totp_input = page.ele("#totpPin", timeout=5) or page.ele('input[type="tel"]', timeout=5)
        if totp_input:
            totp_input.input(code)
            time.sleep(0.5)
            btn = page.ele("#totpNext", timeout=3) or page.ele("text:Next", timeout=3)
            if btn:
                btn.click()
                time.sleep(3)

    # 提取 rapt
    import re
    m = re.search(r'rapt=([^&]+)', page.url)
    rapt = m.group(1) if m else None
    logger.info(f"rapt: {'获取成功' if rapt else '未获取到'}")
    return rapt


def get_rapt_sync(page, target_path: str, password: str, totp_secret: str = "") -> Optional[str]:
    """导航到需要 rapt 的页面, 完成重验证, 返回 rapt token"""
    page.get(f"https://myaccount.google.com{target_path}")
    time.sleep(3)
    return handle_reauth_sync(page, password, totp_secret)
