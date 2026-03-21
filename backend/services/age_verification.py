"""Google 年龄认证 - 信用卡自动填卡

流程:
1. 导航到 myaccount.google.com/age-verification 检测状态
2. 未认证 → 导航到信用卡认证页面
3. 等待 payments.google.com buyflow iframe
4. iframe 内填写卡号/有效期/CVV/邮编 → 提交
5. 等待结果

参考: obeginners/Google-Account-Manager feature/auto-login-module 分支
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

AGE_VERIFICATION_URL = "https://myaccount.google.com/age-verification?hl=en&pli=1&utm_source=p0"
CREDIT_CARD_URL = "https://myaccount.google.com/age-verification/credit-card?hl=en"
BUYFLOW_URL_PATTERN = "payments.google.com"

# 检测选择器 (语言无关)
SEL_LINK_DOCUMENT = 'a[href*="age-verification/document"]'
SEL_LINK_CREDIT_CARD = 'a[href*="age-verification/credit-card"]'
SEL_LINK_SELFIE = 'a[href*="age-verification/selfie"]'
SEL_VERIFIED_CONTAINER = "div.whXP7b"
SEL_UNVERIFIED_SUBTITLE = 'h2[jsname="VdSJob"]'


def check_age_verification(page, on_step=None) -> str:
    """检测年龄认证状态

    Returns: "verified" / "not_verified" / "unknown"
    """
    from services.automation import StepTracker
    tracker = StepTracker("age_check", on_step)

    tracker.step("检测年龄认证", "info", "导航到认证页面...")
    page.get(AGE_VERIFICATION_URL)
    time.sleep(5)

    url = page.url
    if "age-verification" not in url:
        # 可能被重定向了, 再试一次
        time.sleep(3)
        page.get(AGE_VERIFICATION_URL)
        time.sleep(5)
        url = page.url

    if "age-verification" not in url:
        tracker.step("检测年龄认证", "skip", f"无法到达认证页面: {url[:80]}")
        return "unknown"

    # Layer 1: 认证方式链接检测
    has_doc = bool(page.ele(SEL_LINK_DOCUMENT, timeout=2))
    has_card = bool(page.ele(SEL_LINK_CREDIT_CARD, timeout=1))
    has_selfie = bool(page.ele(SEL_LINK_SELFIE, timeout=1))

    if has_doc or has_card or has_selfie:
        tracker.step("检测年龄认证", "fail", "未认证 (检测到认证方式选择)")
        return "not_verified"

    # Layer 2: 已认证页面元素
    has_verified = bool(page.ele(SEL_VERIFIED_CONTAINER, timeout=2))
    has_unverified = bool(page.ele(SEL_UNVERIFIED_SUBTITLE, timeout=1))

    if has_verified and not has_unverified:
        tracker.step("检测年龄认证", "ok", "已认证")
        return "verified"

    # Layer 3: 文本回退
    try:
        text = (page.html or "").lower()
        if "you're all set" in text or "your age is verified" in text:
            tracker.step("检测年龄认证", "ok", "已认证 (文本检测)")
            return "verified"
        if "choose how to verify" in text:
            tracker.step("检测年龄认证", "fail", "未认证 (文本检测)")
            return "not_verified"
    except Exception:
        pass

    tracker.step("检测年龄认证", "skip", f"无法判断, URL: {url[:80]}")
    return "unknown"


def execute_credit_card_verification(page, card_number: str, card_expiry: str,
                                      card_cvv: str, card_zip: str,
                                      on_step=None) -> dict:
    """执行信用卡年龄认证

    Args:
        page: DrissionPage WebPage (已登录)
        card_number: 卡号
        card_expiry: 有效期 MM/YY
        card_cvv: CVV
        card_zip: 邮编

    Returns: {"success": bool, "message": str}
    """
    from services.automation import StepTracker
    tracker = StepTracker("age_verify", on_step)

    try:
        # Step 1: 导航到信用卡认证页面
        tracker.step("导航信用卡页面", "info")
        page.get(CREDIT_CARD_URL)
        time.sleep(5)

        # Step 2: 等待 buyflow iframe
        tracker.step("等待支付表单", "info", "等待 payments.google.com iframe...")
        iframe = None
        for _ in range(30):
            # DrissionPage 查找 iframe
            try:
                frames = page.get_frames()
                for f in frames:
                    if BUYFLOW_URL_PATTERN in (f.url or ""):
                        iframe = f
                        break
            except Exception:
                pass

            if iframe:
                break

            # 备选: 直接在页面中查找 iframe 元素
            iframe_ele = page.ele(f'iframe[src*="{BUYFLOW_URL_PATTERN}"]', timeout=1)
            if iframe_ele:
                try:
                    iframe = iframe_ele.sr
                except Exception:
                    pass

            if iframe:
                break
            time.sleep(1)

        if not iframe:
            return tracker.result(False, "支付表单 iframe 未加载", step="iframe")

        tracker.step("支付表单已加载", "ok")

        # Step 3: 等待表单元素就绪
        tracker.step("等待表单就绪", "info")
        time.sleep(3)

        # Step 4: 填写表单 (在 iframe 内通过 JS 操作)
        # DrissionPage 的 iframe 操作: 用 page.run_js_loaded 在 iframe context 中执行
        fields = [
            ("Card number", card_number, "卡号"),
            ("MM/YY", card_expiry, "有效期"),
            ("Security code", card_cvv, "安全码"),
            ("Billing zip code", card_zip, "邮编"),
        ]

        for label, value, display in fields:
            tracker.step(f"填写{display}", "info", f"{display}: {'*' * (len(value) - 4) + value[-4:] if len(value) > 4 else '****'}")

            # 在 iframe 中执行 JS 填写
            fill_js = f"""
            (function() {{
                var labelText = '{label}';
                var value = '{value}';
                var input = null;
                // 策略1: span 文本匹配 → Material Design 容器 → input
                var spans = document.querySelectorAll('span');
                for (var i = 0; i < spans.length; i++) {{
                    if (spans[i].textContent.trim() === labelText) {{
                        var container = spans[i].closest('div.VfPpkd-fmcmS')
                                     || spans[i].parentElement.parentElement;
                        if (container) {{
                            input = container.querySelector('input');
                            if (input) break;
                        }}
                    }}
                }}
                // 策略2: aria-label
                if (!input) {{
                    input = document.querySelector('input[aria-label*="' + labelText + '"]');
                }}
                // 策略3: placeholder
                if (!input) {{
                    input = document.querySelector('input[placeholder*="' + labelText + '"]');
                }}
                if (!input) return 'not_found';
                input.focus();
                input.value = value;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return 'ok';
            }})()
            """

            try:
                result = iframe.run_js(fill_js)
                if result == "not_found":
                    tracker.step(f"填写{display}", "skip", f"未找到字段: {label}")
                else:
                    tracker.step(f"填写{display}", "ok")
            except Exception as e:
                tracker.step(f"填写{display}", "fail", str(e))

            time.sleep(0.5)

        # Step 5: 点击 "Save and submit"
        tracker.step("提交表单", "info", "点击 Save and submit")
        submit_js = """
        (function() {
            var btns = document.querySelectorAll('button, [role="button"]');
            for (var i = 0; i < btns.length; i++) {
                var text = btns[i].textContent.trim().toLowerCase();
                if (text.indexOf('save') !== -1 && text.indexOf('submit') !== -1) {
                    btns[i].click();
                    return 'clicked';
                }
            }
            return 'not_found';
        })()
        """
        try:
            result = iframe.run_js(submit_js)
            if result == "not_found":
                return tracker.result(False, "未找到 Save and submit 按钮", step="submit")
            tracker.step("提交表单", "ok")
        except Exception as e:
            return tracker.result(False, f"提交失败: {e}", step="submit")

        # Step 6: 等待结果
        tracker.step("等待认证结果", "info")
        for _ in range(15):
            time.sleep(2)
            url = page.url

            # 跳回年龄认证页面(非信用卡) → 可能成功
            if "age-verification" in url and "credit-card" not in url:
                time.sleep(2)
                status = check_age_verification(page)
                if status == "verified":
                    return tracker.result(True, "年龄认证成功")

            # iframe 内检测错误
            try:
                error_js = """
                (function() {
                    var text = document.body ? document.body.innerText : '';
                    var lower = text.toLowerCase();
                    if (lower.indexOf('declined') !== -1 || lower.indexOf('unable to verify') !== -1 ||
                        lower.indexOf('try a different') !== -1) {
                        return 'declined';
                    }
                    if (lower.indexOf('success') !== -1 || lower.indexOf('verified') !== -1 ||
                        lower.indexOf("you're all set") !== -1) {
                        return 'success';
                    }
                    return 'pending';
                })()
                """
                result = iframe.run_js(error_js)
                if result == "declined":
                    return tracker.result(False, "信用卡被拒", step="declined")
                if result == "success":
                    return tracker.result(True, "年龄认证成功")
            except Exception:
                pass

        # 超时最终检查
        final = check_age_verification(page)
        if final == "verified":
            return tracker.result(True, "年龄认证成功 (最终检查)")

        return tracker.result(False, "认证结果超时未知", step="timeout")

    except Exception as e:
        return tracker.result(False, f"年龄认证异常: {e}", step="error")


def check_and_verify_age(page, on_step=None) -> dict:
    """检测年龄认证状态, 未认证则自动填卡

    Returns: {"success": bool, "message": str, "status": str}
    """
    from services.automation import StepTracker
    from models.database import SessionLocal
    from models.orm import Config

    tracker = StepTracker("age", on_step)

    # Step 1: 检测状态
    status = check_age_verification(page, on_step)

    if status == "verified":
        tracker.step("年龄认证", "ok", "已通过")
        return {"success": True, "message": "已通过年龄认证", "status": "verified"}

    if status == "unknown":
        tracker.step("年龄认证", "skip", "无法判断状态")
        return {"success": True, "message": "无法判断年龄认证状态, 继续", "status": "unknown"}

    # Step 2: 未认证 → 读取信用卡配置
    tracker.step("读取信用卡配置", "info")
    db = SessionLocal()
    try:
        card_number = ""
        card_expiry = ""
        card_cvv = ""
        card_zip = ""
        for key in ["card_number", "card_expiry", "card_cvv", "card_zip"]:
            row = db.query(Config).filter(Config.key == key).first()
            if row:
                if key == "card_number": card_number = row.value
                elif key == "card_expiry": card_expiry = row.value
                elif key == "card_cvv": card_cvv = row.value
                elif key == "card_zip": card_zip = row.value
    finally:
        db.close()

    if not card_number or not card_cvv:
        tracker.step("信用卡配置", "fail", "未配置信用卡信息, 请在系统设置中填写")
        return {"success": False, "message": "未配置信用卡, 请在系统设置中填写", "status": "not_verified"}

    tracker.step("信用卡配置", "ok", f"卡号: ****{card_number[-4:]}")

    # Step 3: 执行填卡
    result = execute_credit_card_verification(
        page, card_number, card_expiry, card_cvv, card_zip, on_step
    )
    result["status"] = "verified" if result.get("success") else "not_verified"
    return result
