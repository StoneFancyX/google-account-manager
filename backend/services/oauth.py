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
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

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


# ── API 可用性探测 ─────────────────────────────────────────

ANTIGRAVITY_DAILY_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com"
ANTIGRAVITY_STREAM_PATH = "/v1internal:streamGenerateContent"


def probe_api(access_token: str, project_id: str = "") -> Tuple[bool, str, Optional[str]]:
    """发送一次简单的 streamGenerateContent 请求来探测 API 是否可用

    返回: (可用?, 消息, 验证链接或None)
    - 可用: True 表示 API 正常可用
    - 消息: 成功时为 "API 可用", 失败时为错误详情
    - 验证链接: 需要验证时返回 validation_url, 否则 None
    """
    url = f"{ANTIGRAVITY_DAILY_ENDPOINT}{ANTIGRAVITY_STREAM_PATH}"

    # 构建最小化的 Antigravity 请求
    request_id = f"agent-{uuid.uuid4()}"
    session_id = f"-{int(time.time() * 1000)}"

    payload = {
        "model": "claude-sonnet-4-20250514",
        "userAgent": "antigravity",
        "requestType": "agent",
        "project": project_id or "probe-test-00000",
        "requestId": request_id,
        "request": {
            "sessionId": session_id,
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "hi"}]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 32
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": API_USER_AGENT,
        "X-Goog-Api-Client": API_CLIENT,
        "Client-Metadata": CLIENT_METADATA,
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=30)

        if resp.status_code == 200:
            return True, "API 可用", None

        # 解析错误响应 — Google 返回的是 JSON 数组
        error_text = resp.text
        logger.warning(f"API 探测失败: HTTP {resp.status_code} - {error_text[:500]}")

        validation_url = _extract_validation_url(error_text)
        if validation_url:
            return False, "需要账号验证", validation_url

        return False, f"HTTP {resp.status_code}: {error_text[:500]}", None

    except Exception as e:
        logger.error(f"API 探测异常: {e}")
        return False, f"请求异常: {e}", None


def _extract_validation_url(error_text: str) -> Optional[str]:
    """从 Google API 403 错误响应中提取 validation_url

    Google 返回格式:
    [{"error": {"details": [{"@type": "...ErrorInfo", "metadata": {"validation_url": "..."}}]}}]
    """
    try:
        import json
        data = json.loads(error_text)
        # 响应可能是数组或单个对象
        error_obj = data[0] if isinstance(data, list) else data
        details = error_obj.get("error", {}).get("details", [])
        for detail in details:
            # 从 ErrorInfo 的 metadata 中提取
            metadata = detail.get("metadata", {})
            v_url = metadata.get("validation_url")
            if v_url:
                return v_url
            # 从 Help 的 links 中提取
            for link in detail.get("links", []):
                link_url = link.get("url", "")
                if "accounts.google.com" in link_url:
                    return link_url
    except Exception:
        pass

    # JSON 解析失败时回退到正则
    match = re.search(r'https?://accounts\.google\.com/[^\s"\'<>]+', error_text)
    if match:
        return match.group(0).rstrip('.,;!)')
    return None


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
        # Step 0: 年龄认证检测
        from services.age_verification import check_and_verify_age
        tracker.step("年龄认证检测", "info")
        age_result = check_and_verify_age(page, on_step)
        if age_result.get("status") == "verified":
            tracker.step("年龄认证", "ok", age_result.get("message", "已通过"))
        elif not age_result.get("success"):
            tracker.step("年龄认证", "fail", age_result.get("message", ""))
            return tracker.result(False, age_result.get("message", "年龄认证失败"), step="age_verify")
        else:
            tracker.step("年龄认证", "skip", age_result.get("message", ""))

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

        # Step 7: 探测 API 可用性
        tracker.step("API 探测", "info", "发送测试请求...")
        try:
            api_ok, api_msg, validation_url = probe_api(access_token, project_id)
            if api_ok:
                tracker.step("API 探测", "ok", "API 可用")
            else:
                tracker.step("API 探测", "fail", api_msg)
                if validation_url:
                    tracker.step("验证链接", "info", validation_url)
                    credential["validation_url"] = validation_url

                    # Step 8: 自动手机号验证
                    tracker.step("自动接码验证", "info", "开始自动验证...")
                    verify_result = auto_phone_verify_sync(page, validation_url, on_step)
                    if verify_result.get("success"):
                        tracker.step("自动接码验证", "ok", verify_result.get("message", ""))
                        # 保存最终页面信息
                        credential["verify_final_url"] = page.url
                        try:
                            page.get_screenshot(".verification_final.png")
                        except Exception:
                            pass
                        # 验证成功后重新探测
                        tracker.step("重新探测", "info")
                        api_ok2, api_msg2, _ = probe_api(access_token, project_id)
                        if api_ok2:
                            tracker.step("重新探测", "ok", "API 已可用")
                            credential.pop("validation_url", None)
                        else:
                            tracker.step("重新探测", "fail", api_msg2)
                    else:
                        tracker.step("自动接码验证", "fail", verify_result.get("message", "验证失败"))
        except Exception as e:
            tracker.step("API 探测", "skip", f"探测异常: {e}")

        return tracker.result(True, "OAuth 认证成功", extra={"credential": credential})

    except Exception as e:
        return tracker.result(False, f"OAuth 异常: {e}", step="error")


# ── 自动手机号验证 ─────────────────────────────────────

def auto_phone_verify_sync(page, validation_url: str, on_step=None) -> dict:
    """用已登录浏览器自动完成 Google 手机号验证

    流程:
    1. 打开 validation_url → 选择 "Verify your phone number"
    2. 从接码平台购买号码
    3. 输入手机号 → 点 Next
    4. 轮询等待验证码
    5. 输入验证码 → 完成

    Args:
        page: DrissionPage WebPage 实例 (已登录)
        validation_url: Google 验证链接
        on_step: 步骤回调

    Returns:
        {"success": bool, "message": str}
    """
    from services.automation import StepTracker
    from models.database import SessionLocal
    from models.orm import Config, SmsProvider
    from services.sms_api import create_provider

    tracker = StepTracker("phone_verify", on_step)

    try:
        # Step 1: 获取接码提供商
        tracker.step("获取接码配置", "info")
        db = SessionLocal()
        try:
            # 读取默认提供商
            row = db.query(Config).filter(Config.key == "default_sms_provider_id").first()
            provider = None
            if row:
                provider = db.query(SmsProvider).get(int(row.value))
            if not provider:
                provider = db.query(SmsProvider).first()
            if not provider or not provider.api_key:
                return tracker.result(False, "未配置接码提供商", step="sms_config")

            sms_api = create_provider(provider.provider_type, provider.api_key)
            service = provider.default_service or "go"
            country = provider.default_country or 2
            tracker.step("接码配置", "ok", f"{provider.name} | 服务={service} 国家={country}")
        finally:
            db.close()

        # Step 2: 打开验证页面
        tracker.step("打开验证页面", "info")
        page.get(validation_url)
        time.sleep(5)

        # Step 3: 选择 "Verify your phone number"
        if "uplevelingstep/selection" in page.url:
            tracker.step("选择验证方式", "info", "选择手机号验证")
            phone_option = None
            for sel in ["text:Verify your phone number", "text:验证您的电话号码", "text:phone number"]:
                phone_option = page.ele(sel, timeout=3)
                if phone_option:
                    break
            if not phone_option:
                return tracker.result(False, "未找到手机验证选项", step="select_method")
            phone_option.click()
            time.sleep(4)
            tracker.step("选择验证方式", "ok")

        # Step 4: 购买号码
        tracker.step("购买号码", "info", f"服务={service} 国家={country}")
        ok, number_data = sms_api.get_number(service=service, country=country)
        if not ok:
            return tracker.result(False, f"购买号码失败: {number_data}", step="buy_number")

        activation_id = number_data["activation_id"]
        phone_number = number_data["phone_number"]
        tracker.step("号码已购买", "ok", phone_number)

        # Step 5: 输入手机号
        tracker.step("输入手机号", "info", phone_number)

        # 查找手机号输入框
        phone_input = page.ele("#phoneNumberId", timeout=5) or page.ele("input[type='tel']", timeout=3)
        if not phone_input:
            sms_api.cancel(activation_id)
            return tracker.result(False, "找不到手机号输入框", step="phone_input")

        # 输入带+号的完整号码, Google 会自动切换国家
        phone_with_plus = f"+{phone_number}" if not phone_number.startswith("+") else phone_number
        phone_input.clear()
        phone_input.input(phone_with_plus)
        time.sleep(1)

        # 点 Next
        next_btn = (
            page.ele("text:Next", timeout=3)
            or page.ele("text:下一步", timeout=2)
            or page.ele("#next", timeout=2)
            or page.ele("text:Send", timeout=2)
        )
        if next_btn:
            next_btn.click()
            time.sleep(4)
        tracker.step("已发送验证码", "ok")

        # 检查是否有错误 (号码无效等)
        error_ele = (
            page.ele("text:This phone number cannot be used", timeout=2)
            or page.ele("text:didn't recognize", timeout=1)
            or page.ele("text:无法使用此电话号码", timeout=1)
        )
        if error_ele:
            sms_api.cancel(activation_id)
            return tracker.result(False, f"号码被拒绝: {phone_number}", step="phone_rejected")

        # Step 6: 等待验证码
        tracker.step("等待验证码", "info", f"轮询中 (activation={activation_id})")
        code_ok, code, sms_text = sms_api.wait_for_code(activation_id, timeout=120, interval=5)
        if not code_ok:
            sms_api.cancel(activation_id)
            return tracker.result(False, f"未收到验证码: {sms_text}", step="wait_code")
        tracker.step("收到验证码", "ok", code)

        # Step 7: 输入验证码
        tracker.step("输入验证码", "info", code)

        # 查找验证码输入框 (Google 用 #idvAnyPhonePin)
        code_input = (
            page.ele("#idvAnyPhonePin", timeout=5)
            or page.ele("#code", timeout=3)
            or page.ele("input[type='tel']", timeout=3)
        )
        if not code_input:
            sms_api.finish(activation_id)
            return tracker.result(False, "找不到验证码输入框", step="code_input")

        code_input.clear()
        # 输入框预填了 "G-", 只需输入纯数字验证码
        code_input.input(code)
        time.sleep(1)

        # 点确认 (Google 用 #idvanyphoneverifyNext)
        verify_btn = (
            page.ele("#idvanyphoneverifyNext", timeout=3)
            or page.ele("text:Next", timeout=2)
            or page.ele("text:Verify", timeout=2)
            or page.ele("text:下一步", timeout=2)
        )
        if verify_btn:
            verify_btn.click()
            time.sleep(5)

        # Step 8: 完成激活
        sms_api.finish(activation_id)
        tracker.step("验证完成", "ok")

        # 检查是否成功 (页面跳转到成功页)
        current_url = page.url
        if "auth_success" in current_url or "gemini-code-assist" in current_url or "myaccount" in current_url:
            return tracker.result(True, "手机号验证成功")

        # 可能还在验证页面, 检查是否有错误
        error_ele2 = page.ele("text:Wrong code", timeout=2) or page.ele("text:验证码错误", timeout=1)
        if error_ele2:
            return tracker.result(False, "验证码错误", step="wrong_code")

        # 不确定是否成功, 返回当前 URL
        return tracker.result(True, f"验证流程已完成, URL: {current_url[:80]}")

    except Exception as e:
        return tracker.result(False, f"自动验证异常: {e}", step="error")
