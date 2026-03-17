"""邮箱/短信验证码获取服务

支持两种验证码获取方式:
1. SMS API (umlmail.site 等): 直接返回验证码
   - URL 格式: https://umlmail.site/Mail/GetCodeSMS?token=xxx
   - 返回: {"success": true/false, "message": "验证码或错误"}

2. Webhook 邮件 API (webhook.style 等): 从邮件中提取验证码
   - URL 格式: https://webhook.style/recovery-messages/TOKEN
   - 邮件 API: https://webhook.style/recovery-mails/get/TOKEN
   - 刷新 API: https://webhook.style/recovery-mails/update/TOKEN
   - 邮件 subject 含验证码: "Email verification code: 123456"
"""
import re
import time
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger(__name__)

# 验证码正则: 6位数字
CODE_PATTERN = re.compile(r'\b(\d{6})\b')
# Google 验证码邮件 subject 正则
SUBJECT_CODE_PATTERN = re.compile(r'(?:verification code|验证码)[:\s]*(\d{6})', re.IGNORECASE)


def extract_verification_link(notes: str) -> Optional[str]:
    """从 notes 字段中提取验证链接"""
    if not notes:
        return None
    # 匹配 URL
    urls = re.findall(r'https?://\S+', notes)
    for url in urls:
        # 去掉末尾的标点
        url = url.rstrip('.,;!)')
        return url
    return None


def _detect_link_type(url: str) -> str:
    """检测链接类型: 'sms_api' 或 'webhook_mail'"""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # SMS API 类型: URL 中含 GetCode/GetCodeSMS 等关键词
    if "GetCode" in url or "getcode" in url.lower():
        return "sms_api"

    # webhook.style 类型
    if "webhook.style" in host:
        return "webhook_mail"

    # 默认尝试当作 SMS API
    return "sms_api"


def _fetch_code_from_sms_api(url: str, max_retries: int = 3, interval: float = 5.0) -> Tuple[bool, str]:
    """从 SMS API 获取验证码

    返回: (成功?, 验证码或错误信息)
    """
    for attempt in range(max_retries):
        try:
            # 确保 https
            if url.startswith("http://"):
                url = "https://" + url[7:]

            resp = requests.get(url, timeout=15, allow_redirects=True)
            data = resp.json()

            if data.get("success"):
                code = str(data.get("message", "")).strip()
                if code and CODE_PATTERN.match(code):
                    logger.info(f"SMS API 获取验证码成功: {code}")
                    return True, code
                # message 可能包含验证码
                match = CODE_PATTERN.search(code)
                if match:
                    logger.info(f"SMS API 提取验证码成功: {match.group(1)}")
                    return True, match.group(1)
                return True, code

            logger.info(f"SMS API 第 {attempt+1} 次未获取到验证码: {data.get('message', '')}")
        except Exception as e:
            logger.warning(f"SMS API 请求失败 (第 {attempt+1} 次): {e}")

        if attempt < max_retries - 1:
            time.sleep(interval)

    return False, "SMS API 多次重试后未获取到验证码"


def _extract_token_from_webhook_url(url: str) -> str:
    """从 webhook.style URL 中提取 token"""
    # https://webhook.style/recovery-messages/TOKEN
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    # 取最后一段作为 token
    parts = path.split("/")
    return parts[-1] if parts else ""


def _fetch_code_from_webhook(url: str, max_retries: int = 3, interval: float = 5.0) -> Tuple[bool, str]:
    """从 webhook.style 邮件 API 获取验证码

    返回: (成功?, 验证码或错误信息)
    """
    token = _extract_token_from_webhook_url(url)
    if not token:
        return False, "无法从 webhook URL 提取 token"

    base_url = "https://webhook.style/recovery-mails"

    for attempt in range(max_retries):
        try:
            # 先刷新邮箱
            if attempt > 0:
                try:
                    requests.get(f"{base_url}/update/{token}", timeout=15)
                    time.sleep(3)  # 等待邮件同步
                except Exception:
                    pass

            # 获取邮件列表
            resp = requests.get(f"{base_url}/get/{token}", timeout=15)
            data = resp.json()

            mails = data.get("mails", [])
            if not mails:
                logger.info(f"Webhook 第 {attempt+1} 次: 暂无邮件")
                if attempt < max_retries - 1:
                    time.sleep(interval)
                continue

            # 按时间倒序, 取最新的 Google 验证邮件
            # 邮件已按时间排序, 最后一封最新 (或第一封最新, 取决于 API)
            for mail in reversed(mails):
                subject = mail.get("subject", "")
                from_addr = mail.get("from", "")
                plain = mail.get("plain", "")

                # 只处理 Google 发的邮件
                if "google" not in from_addr.lower() and "google" not in subject.lower():
                    continue

                # 从 subject 提取验证码
                match = SUBJECT_CODE_PATTERN.search(subject)
                if match:
                    code = match.group(1)
                    logger.info(f"Webhook 从 subject 提取验证码: {code}")
                    return True, code

                # 从 subject 直接提取 6 位数字
                match = CODE_PATTERN.search(subject)
                if match:
                    code = match.group(1)
                    logger.info(f"Webhook 从 subject 提取数字: {code}")
                    return True, code

                # 从正文提取
                match = CODE_PATTERN.search(plain)
                if match:
                    code = match.group(1)
                    logger.info(f"Webhook 从正文提取验证码: {code}")
                    return True, code

            logger.info(f"Webhook 第 {attempt+1} 次: 邮件中未找到验证码")
        except Exception as e:
            logger.warning(f"Webhook 请求失败 (第 {attempt+1} 次): {e}")

        if attempt < max_retries - 1:
            time.sleep(interval)

    return False, "Webhook 多次重试后未获取到验证码"


def fetch_verification_code(
    url: str,
    max_retries: int = 6,
    interval: float = 5.0,
) -> Tuple[bool, str]:
    """统一接口: 根据 URL 类型自动选择获取方式

    参数:
        url: 验证链接 (SMS API 或 webhook URL)
        max_retries: 最大重试次数
        interval: 重试间隔 (秒)

    返回: (成功?, 验证码或错误信息)
    """
    link_type = _detect_link_type(url)
    logger.info(f"验证码获取: type={link_type}, url={url[:80]}...")

    if link_type == "webhook_mail":
        return _fetch_code_from_webhook(url, max_retries, interval)
    else:
        return _fetch_code_from_sms_api(url, max_retries, interval)
