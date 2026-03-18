"""Google OAuth 自动化服务 - 使用已登录浏览器自动完成 OAuth 授权

流程:
  1. 构建 OAuth 授权 URL (antigravity 的 client_id + scopes)
  2. 用已登录的 DrissionPage 浏览器打开 URL → 自动同意授权
  3. 处理可能的 2FA 验证 / 密码重验证
  4. 从回调 URL 中提取 authorization code
  5. 用 code 换取 access_token + refresh_token
  6. 获取 project_id (via loadCodeAssist)
  7. 生成认证 JSON
"""

import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import pyotp

from services.browser import browser_manager

logger = logging.getLogger(__name__)

# ── OAuth 常量 (Google Cloud Code / Antigravity 内置客户端凭据) ───────

CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
CLIENT_SECRET = "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"

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo?alt=json"

API_ENDPOINT = "https://cloudcode-pa.googleapis.com"
API_VERSION = "v1internal"
API_USER_AGENT = "google-api-nodejs-client/9.15.1"
API_CLIENT = "google-cloud-sdk vscode_cloudshelleditor/0.1"
CLIENT_METADATA = '{"ideType":"IDE_UNSPECIFIED","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}'

# OAuth 回调使用 localhost 重定向 (无需真正的回调服务器, 浏览器会导航到该 URL)
REDIRECT_URI = "http://localhost:51121/oauth-callback"


# ── 工具函数 ─────────────────────────────────────────────


def build_auth_url(state: str) -> str:
    """构建 Google OAuth 授权 URL"""
    from urllib.parse import urlencode
    params = {
        "access_type": "offline",
        "client_id": CLIENT_ID,
        "prompt": "consent",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict:
    """用 authorization code 换取 access_token + refresh_token"""
    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    resp = httpx.post(
        TOKEN_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token 交换失败: HTTP {resp.status_code} - {resp.text[:200]}")
    return resp.json()


def fetch_user_info(access_token: str) -> str:
    """用 access_token 获取用户邮箱"""
    resp = httpx.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取用户信息失败: HTTP {resp.status_code}")
    return resp.json().get("email", "")


def fetch_project_id(access_token: str) -> str:
    """通过 loadCodeAssist 获取 GCP project ID"""
    url = f"{API_ENDPOINT}/{API_VERSION}:loadCodeAssist"
    body = {
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }
    }
    resp = httpx.post(
        url,
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": API_USER_AGENT,
            "X-Goog-Api-Client": API_CLIENT,
            "Client-Metadata": CLIENT_METADATA,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        # 尝试 onboard
        return _onboard_user(access_token)

    data = resp.json()
    project_id = ""
    if isinstance(data.get("cloudaicompanionProject"), str):
        project_id = data["cloudaicompanionProject"].strip()
    elif isinstance(data.get("cloudaicompanionProject"), dict):
        project_id = data["cloudaicompanionProject"].get("id", "").strip()

    if not project_id:
        # 尝试从 allowedTiers 获取 tierID, 然后 onboard
        tier_id = "legacy-tier"
        for tier in data.get("allowedTiers", []):
            if isinstance(tier, dict) and tier.get("isDefault"):
                tid = tier.get("id", "").strip()
                if tid:
                    tier_id = tid
                    break
        project_id = _onboard_user(access_token, tier_id)

    return project_id


def _onboard_user(access_token: str, tier_id: str = "legacy-tier") -> str:
    """通过 onboardUser 获取 project ID (轮询模式)"""
    url = f"{API_ENDPOINT}/{API_VERSION}:onboardUser"
    body = {
        "tierId": tier_id,
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }
    }

    for attempt in range(5):
        resp = httpx.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": API_USER_AGENT,
                "X-Goog-Api-Client": API_CLIENT,
                "Client-Metadata": CLIENT_METADATA,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"onboardUser 失败: HTTP {resp.status_code} - {resp.text[:200]}")

        data = resp.json()
        if data.get("done"):
            response_data = data.get("response", {})
            project = response_data.get("cloudaicompanionProject", "")
            if isinstance(project, dict):
                return project.get("id", "").strip()
            if isinstance(project, str):
                return project.strip()
            return ""

        time.sleep(2)

    return ""


# ── 浏览器页面交互辅助 ─────────────────────────────────


def _check_for_code(url: str) -> Optional[str]:
    """从 URL 中提取 authorization code"""
    if "localhost:51121/oauth-callback" in url or ("code=" in url and "accounts.google" not in url):
        m = re.search(r'[?&]code=([^&]+)', url)
        if m:
            return m.group(1)
    return None


def _check_for_error(url: str) -> Optional[str]:
    """从 URL 中提取 error"""
    if "error=" in url and "localhost" in url:
        m = re.search(r'[?&]error=([^&]+)', url)
        return m.group(1) if m else "unknown"
    return None


def _is_password_page(page) -> bool:
    """检测是否在密码输入页面"""
    url = page.url
    if "challenge/pwd" in url or "signin/v2/challenge/password" in url:
        return True
    # 检查是否有密码输入框
    pwd = page.ele("@name=Passwd", timeout=0.5) or page.ele('input[type="password"]', timeout=0.5)
    return bool(pwd)


def _is_totp_page(page) -> bool:
    """检测是否在 2FA/TOTP 验证页面"""
    url = page.url
    if "challenge/totp" in url or "challenge/selection" in url:
        return True
    totp_input = page.ele("#totpPin", timeout=0.5) or page.ele('input[type="tel"]', timeout=0.5)
    return bool(totp_input)


def _handle_password(page, password: str, tracker) -> bool:
    """处理密码输入页面，返回是否成功"""
    pwd_input = page.ele("@name=Passwd", timeout=3) or page.ele('input[type="password"]', timeout=3)
    if not pwd_input:
        tracker.step("密码验证", "fail", "找不到密码输入框")
        return False

    pwd_input.input(password)
    time.sleep(0.5)
    next_btn = (
        page.ele("#passwordNext", timeout=3)
        or page.ele("text:Next", timeout=2)
        or page.ele("text:下一步", timeout=2)
    )
    if next_btn:
        next_btn.click()
        time.sleep(3)
    tracker.step("密码验证", "ok")
    return True


def _handle_totp(page, totp_secret: str, tracker) -> bool:
    """处理 2FA/TOTP 验证页面，返回是否成功"""
    if not totp_secret:
        tracker.step("2FA 验证", "fail", "需要 2FA 但账号未配置 TOTP")
        return False

    code = pyotp.TOTP(totp_secret.replace(' ', '')).now()

    # 如果在 challenge/selection 页面, 先选择 Authenticator
    if "challenge/selection" in page.url:
        opt = (
            page.ele("text:Authenticator", timeout=3)
            or page.ele("text:Google Authenticator", timeout=2)
            or page.ele("text:验证器", timeout=2)
        )
        if opt:
            opt.click()
            time.sleep(2)

    totp_input = page.ele("#totpPin", timeout=5) or page.ele('input[type="tel"]', timeout=5)
    if not totp_input:
        tracker.step("2FA 验证", "fail", "找不到 TOTP 输入框")
        return False

    totp_input.input(code)
    time.sleep(0.5)
    btn = (
        page.ele("#totpNext", timeout=3)
        or page.ele("text:Next", timeout=2)
        or page.ele("text:下一步", timeout=2)
    )
    if btn:
        btn.click()
        time.sleep(3)

    tracker.step("2FA 验证", "ok", f"已输入验证码")
    return True


def _try_click_consent_buttons(page) -> bool:
    """尝试点击 OAuth 同意页面上的各种按钮, 返回是否点击了按钮"""
    # Google OAuth 同意页面上的各种按钮变体
    selectors = [
        "#submit_approve_access",           # OAuth 同意页 "Allow" 按钮
        "text:Allow",                       # Allow 文字按钮
        "text:允许",                        # 中文 Allow
        "text:Continue",                    # Continue 按钮
        "text:继续",                        # 中文 Continue
        'button:has-text("Allow")',         # button 内含 Allow
        'button:has-text("Continue")',      # button 内含 Continue
    ]
    for sel in selectors:
        try:
            btn = page.ele(sel, timeout=0.5)
            if btn:
                btn.click()
                return True
        except Exception:
            continue
    return False


# ── 浏览器自动 OAuth (核心) ─────────────────────────────


def oauth_sync(page, on_step=None, password: str = "", totp_secret: str = ""):
    """用已登录的浏览器自动完成 OAuth 授权流程

    Args:
        page: DrissionPage 的 WebPage 实例 (已登录 Google)
        on_step: 步骤回调函数
        password: 账号密码 (用于密码重验证)
        totp_secret: TOTP 密钥 (用于 2FA 验证)

    Returns:
        AutomationResult
    """
    from services.automation import StepTracker, AutomationResult

    tracker = StepTracker("oauth", on_step)

    try:
        # Step 1: 构建 OAuth URL
        state = secrets.token_urlsafe(32)
        auth_url = build_auth_url(state)
        tracker.step("构建 OAuth URL", "ok")

        # Step 2: 浏览器打开 OAuth URL
        tracker.step("打开授权页面", "info", "导航到 Google OAuth...")
        page.get(auth_url)
        time.sleep(3)

        # Step 3: 处理授权页面循环
        # 可能遇到: 选择账号 → 密码验证 → 2FA 验证 → 同意授权 → 回调
        tracker.step("处理授权", "info", "检查授权页面...")
        max_wait = 60  # 增加等待时间, 因为可能需要 2FA
        code = None
        password_handled = False
        totp_handled = False

        for tick in range(max_wait):
            current_url = page.url

            # 1) 检查是否已经回调 (拿到 code)
            code = _check_for_code(current_url)
            if code:
                break

            # 2) 检查是否有 error
            error = _check_for_error(current_url)
            if error:
                return tracker.result(False, f"授权被拒绝: {error}", step="auth")

            # 3) 密码重验证页面
            if not password_handled and _is_password_page(page):
                if not password:
                    return tracker.result(False, "需要密码重验证但账号无密码", step="password")
                if _handle_password(page, password, tracker):
                    password_handled = True
                    continue
                else:
                    return tracker.result(False, "密码验证失败", step="password")

            # 4) 2FA/TOTP 验证页面
            if not totp_handled and _is_totp_page(page):
                if _handle_totp(page, totp_secret, tracker):
                    totp_handled = True
                    continue
                else:
                    return tracker.result(False, "2FA 验证失败", step="totp")

            # 5) 尝试点击 OAuth 同意按钮
            if _try_click_consent_buttons(page):
                tracker.step("点击授权按钮", "ok")
                time.sleep(3)
                continue

            # 6) 如果页面要求选择账号, 点击第一个
            account_btn = page.ele("@data-identifier", timeout=0.5)
            if account_btn:
                try:
                    account_btn.click()
                    tracker.step("选择账号", "ok")
                    time.sleep(3)
                    continue
                except Exception:
                    pass

            # 7) 检查是否有 "Check your phone" 类型的等待提示 (Google Prompt)
            if "challenge" in current_url and not _is_password_page(page) and not _is_totp_page(page):
                if tick % 5 == 0:
                    tracker.step("等待验证", "info", f"请在手机上确认或等待... ({tick}s)")

            time.sleep(1)

        if not code:
            # 最后一次检查 URL
            final_url = page.url
            code = _check_for_code(final_url)
            if not code:
                return tracker.result(False, f"授权超时, 未获取到 code. URL: {final_url[:100]}", step="auth")

        tracker.step("获取授权码", "ok", f"code: {code[:20]}...")

        # Step 4: 交换 token
        tracker.step("交换 Token", "info", "用 code 换取 access_token...")
        token_resp = exchange_code_for_tokens(code)
        access_token = token_resp.get("access_token", "")
        refresh_token = token_resp.get("refresh_token", "")
        expires_in = token_resp.get("expires_in", 3599)

        if not access_token:
            return tracker.result(False, "Token 交换返回空 access_token", step="token")
        tracker.step("Token 获取成功", "ok")

        # Step 5: 获取 project_id
        tracker.step("获取 Project ID", "info", "调用 loadCodeAssist...")
        project_id = ""
        try:
            project_id = fetch_project_id(access_token)
            if project_id:
                tracker.step("Project ID", "ok", project_id)
            else:
                tracker.step("Project ID", "skip", "未获取到, 不影响使用")
        except Exception as e:
            tracker.step("Project ID", "skip", f"获取失败: {e}")

        # Step 6: 构建认证 JSON
        now = datetime.now(timezone.utc)
        credential = {
            "type": "antigravity",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "timestamp": int(now.timestamp() * 1000),
            "expired": (now + timedelta(seconds=expires_in)).isoformat(),
        }
        if project_id:
            credential["project_id"] = project_id

        tracker.step("认证文件生成", "ok")
        return tracker.result(True, "OAuth 认证成功", extra={"credential": credential})

    except Exception as e:
        return tracker.result(False, f"OAuth 异常: {e}", step="error")
