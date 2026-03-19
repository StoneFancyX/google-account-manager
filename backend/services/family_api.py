"""Google Family Group batchexecute RPC 封装 (纯 httpx)

架构: 浏览器登录 → 提取 Cookies → httpx 纯 HTTP 操作

纯 HTTP 操作 (无需浏览器):
  - query_status()      查询家庭组状态     DmVhMc
  - query_members()     查询成员列表       V2esPe
  - create_family()     创建家庭组         nKULBd → Wffnob → c5gch
  - send_invite()       发送邀请           B3vhdd → xN05r
  - accept_invite()     接受邀请           SZ903d

需要 rapt token 的操作 (浏览器做密码重验证, RPC 本身仍是纯 HTTP):
  - remove_member()     移除成员           Csu7b
  - leave_family()      退出家庭组         Csu7b + "me"
  - delete_family()     删除家庭组         hQih3e
"""

import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://myaccount.google.com"
BATCHEXECUTE_URL = f"{BASE_URL}/_/AccountSettingsUi/data/batchexecute"

ROLE_ADMIN = 1
ROLE_MEMBER = 2
ROLE_NAMES = {ROLE_ADMIN: "admin", ROLE_MEMBER: "member"}


class TokenError(Exception):
    """页面 token 提取失败"""


class RPCError(Exception):
    """batchexecute RPC 调用失败"""

    def __init__(self, rpc_id: str, status_code: int, detail: str = ""):
        self.rpc_id = rpc_id
        self.status_code = status_code
        super().__init__(f"[{rpc_id}] HTTP {status_code}" + (f": {detail}" if detail else ""))


class NoInvitationError(Exception):
    """没有待接受的邀请"""


# ── 工具函数 ──────────────────────────────────────────────

# Google Terms 页面可能出现的国家/地区英文 → 中文映射
_COUNTRY_CN_MAP = {
    "Afghanistan": "阿富汗", "Albania": "阿尔巴尼亚", "Algeria": "阿尔及利亚",
    "Andorra": "安道尔", "Angola": "安哥拉", "Argentina": "阿根廷",
    "Armenia": "亚美尼亚", "Australia": "澳大利亚", "Austria": "奥地利",
    "Azerbaijan": "阿塞拜疆", "Bahrain": "巴林", "Bangladesh": "孟加拉国",
    "Belarus": "白俄罗斯", "Belgium": "比利时", "Belize": "伯利兹",
    "Benin": "贝宁", "Bhutan": "不丹", "Bolivia": "玻利维亚",
    "Bosnia and Herzegovina": "波斯尼亚和黑塞哥维那",
    "Botswana": "博茨瓦纳", "Brazil": "巴西", "Brunei": "文莱",
    "Bulgaria": "保加利亚", "Burkina Faso": "布基纳法索",
    "Cabo Verde": "佛得角", "Cambodia": "柬埔寨", "Cameroon": "喀麦隆",
    "Canada": "加拿大", "Chad": "乍得", "Chile": "智利", "China": "中国",
    "Colombia": "哥伦比亚", "Congo": "刚果", "Costa Rica": "哥斯达黎加",
    "Côte d'Ivoire": "科特迪瓦", "Croatia": "克罗地亚", "Cyprus": "塞浦路斯",
    "Czechia": "捷克", "Czech Republic": "捷克",
    "Denmark": "丹麦", "Dominican Republic": "多米尼加共和国",
    "Ecuador": "厄瓜多尔", "Egypt": "埃及", "El Salvador": "萨尔瓦多",
    "Estonia": "爱沙尼亚", "Ethiopia": "埃塞俄比亚", "Fiji": "斐济",
    "Finland": "芬兰", "France": "法国", "Gabon": "加蓬", "Georgia": "格鲁吉亚",
    "Germany": "德国", "Ghana": "加纳", "Greece": "希腊",
    "Guatemala": "危地马拉", "Guinea": "几内亚", "Haiti": "海地",
    "Honduras": "洪都拉斯", "Hong Kong": "中国香港",
    "Hungary": "匈牙利", "Iceland": "冰岛", "India": "印度",
    "Indonesia": "印度尼西亚", "Iraq": "伊拉克", "Ireland": "爱尔兰",
    "Israel": "以色列", "Italy": "意大利", "Jamaica": "牙买加",
    "Japan": "日本", "Jordan": "约旦", "Kazakhstan": "哈萨克斯坦",
    "Kenya": "肯尼亚", "Kuwait": "科威特", "Kyrgyzstan": "吉尔吉斯斯坦",
    "Laos": "老挝", "Latvia": "拉脱维亚", "Lebanon": "黎巴嫩",
    "Libya": "利比亚", "Liechtenstein": "列支敦士登", "Lithuania": "立陶宛",
    "Luxembourg": "卢森堡", "Macao": "中国澳门", "Madagascar": "马达加斯加",
    "Malawi": "马拉维", "Malaysia": "马来西亚", "Mali": "马里",
    "Malta": "马耳他", "Mauritius": "毛里求斯", "Mexico": "墨西哥",
    "Moldova": "摩尔多瓦", "Mongolia": "蒙古", "Montenegro": "黑山",
    "Morocco": "摩洛哥", "Mozambique": "莫桑比克", "Myanmar": "缅甸",
    "Namibia": "纳米比亚", "Nepal": "尼泊尔", "Netherlands": "荷兰",
    "New Zealand": "新西兰", "Nicaragua": "尼加拉瓜", "Niger": "尼日尔",
    "Nigeria": "尼日利亚", "North Macedonia": "北马其顿", "Norway": "挪威",
    "Oman": "阿曼", "Pakistan": "巴基斯坦", "Palestine": "巴勒斯坦",
    "Panama": "巴拿马", "Papua New Guinea": "巴布亚新几内亚",
    "Paraguay": "巴拉圭", "Peru": "秘鲁", "Philippines": "菲律宾",
    "Poland": "波兰", "Portugal": "葡萄牙", "Qatar": "卡塔尔",
    "Romania": "罗马尼亚", "Russia": "俄罗斯", "Rwanda": "卢旺达",
    "Saudi Arabia": "沙特阿拉伯", "Senegal": "塞内加尔", "Serbia": "塞尔维亚",
    "Singapore": "新加坡", "Slovakia": "斯洛伐克", "Slovenia": "斯洛文尼亚",
    "South Africa": "南非", "South Korea": "韩国", "Spain": "西班牙",
    "Sri Lanka": "斯里兰卡", "Sweden": "瑞典", "Switzerland": "瑞士",
    "Taiwan": "中国台湾", "Tajikistan": "塔吉克斯坦", "Tanzania": "坦桑尼亚",
    "Thailand": "泰国", "Togo": "多哥", "Trinidad and Tobago": "特立尼达和多巴哥",
    "Tunisia": "突尼斯", "Turkey": "土耳其", "Türkiye": "土耳其",
    "Turkmenistan": "土库曼斯坦", "Uganda": "乌干达", "Ukraine": "乌克兰",
    "United Arab Emirates": "阿联酋", "United Kingdom": "英国",
    "United States": "美国", "Uruguay": "乌拉圭", "Uzbekistan": "乌兹别克斯坦",
    "Venezuela": "委内瑞拉", "Vietnam": "越南", "Yemen": "也门",
    "Zambia": "赞比亚", "Zimbabwe": "津巴布韦",
}


def _country_to_chinese(country_en: str) -> str:
    """英文国家名 → 中文, 未知则返回原文"""
    if not country_en:
        return ""
    return _COUNTRY_CN_MAP.get(country_en, country_en)


def parse_response(text: str, rpc_id: str) -> Any:
    """解析 batchexecute 响应, 提取 RPC 返回的 JSON 数据"""
    clean = text[4:] if text.startswith(")]}'") else text
    for line in clean.split("\n"):
        line = line.strip()
        if not line or line.isdigit():
            continue
        if rpc_id not in line:
            continue
        try:
            outer = json.loads(line)
            for item in outer:
                if isinstance(item, list) and len(item) > 2 and item[1] == rpc_id:
                    inner = item[2]
                    return json.loads(inner) if isinstance(inner, str) else inner
        except (json.JSONDecodeError, IndexError, TypeError):
            continue
    return None


def extract_tokens(html: str) -> dict[str, str]:
    """从页面 HTML 的 WIZ_global_data 中提取认证 token"""
    tokens: dict[str, str] = {}
    for key, pattern in {
        "at": r'"SNlM0e":"([^"]+)"',
        "f.sid": r'"FdrFJe":"([^"]+)"',
        "bl": r'"cfb2h":"([^"]+)"',
    }.items():
        m = re.search(pattern, html)
        if m:
            tokens[key] = m.group(1)
    return tokens


# ── 核心 API 类 ───────────────────────────────────────────


class FamilyAPI:
    """Google Family Group 纯 HTTP API

    Usage:
        with FamilyAPI(cookies) as api:
            status = api.query_status()
            members = api.query_members()
            api.create_family()
            api.send_invite("someone@gmail.com")
    """

    def __init__(self, cookies: dict[str, str]):
        self.client = httpx.Client(
            cookies=cookies,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=30,
        )
        self._tokens: dict[str, str] = {}
        self.refresh_tokens()

    # ── 内部方法 ──

    def refresh_tokens(self, source_path: str = "/family/details") -> None:
        """访问页面并提取 WIZ_global_data token (at, f.sid, bl)"""
        resp = self.client.get(f"{BASE_URL}{source_path}")
        resp.raise_for_status()
        self._tokens = extract_tokens(resp.text)
        if "at" not in self._tokens:
            raise TokenError(f"无法从 {source_path} 提取 XSRF token")
        logger.debug("tokens refreshed from %s", source_path)

    def _rpc(
        self,
        rpc_id: str,
        payload: str,
        source_path: str = "/family/details",
        rapt: Optional[str] = None,
        seq: str = "generic",
    ) -> dict[str, Any]:
        """发送 batchexecute RPC 请求"""
        params: dict[str, str] = {
            "rpcids": rpc_id,
            "source-path": source_path,
            "f.sid": self._tokens["f.sid"],
            "bl": self._tokens["bl"],
            "hl": "en",
            "soc-app": "1",
            "soc-platform": "1",
            "soc-device": "1",
            "_reqid": "100001",
            "rt": "c",
        }
        if rapt:
            params["rapt"] = rapt

        url = f"{BATCHEXECUTE_URL}?{urlencode(params)}"
        body = urlencode({
            "f.req": json.dumps([[[rpc_id, payload, None, seq]]]),
            "at": self._tokens["at"],
        })

        resp = self.client.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Same-Domain": "1",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}{source_path}",
            },
        )

        parsed = parse_response(resp.text, rpc_id)
        logger.info("[%s] HTTP %d, raw_len=%d", rpc_id, resp.status_code, len(resp.text))

        return {"status_code": resp.status_code, "raw": resp.text, "parsed": parsed}

    # ── 纯 HTTP 操作 ──

    def query_status(self) -> dict:
        """查询家庭组状态 (DmVhMc)"""
        data = self._rpc("DmVhMc", "[]")["parsed"]
        if data is None:
            return {"has_family": False, "remaining_slots": None}
        return {
            "has_family": bool(data[0]),
            "remaining_slots": data[3] if data[0] else None,
        }

    def query_country(self) -> dict:
        """查询账号所属国家/地区

        访问 https://policies.google.com/terms?hl=en 页面,
        提取 "Country version: XXX" 字段, 并翻译为中文。

        返回: {'country': '英文国家名', 'country_cn': '中文国家名'}
        """
        try:
            resp = self.client.get("https://policies.google.com/terms?hl=en")
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[country] 获取 terms 页面失败: {e}")
            return {"country": "", "country_cn": ""}

        m = re.search(r"Country version:\s*</[^>]+>\s*([^<]+)", resp.text)
        country = m.group(1).strip() if m else ""
        country_cn = _country_to_chinese(country)
        logger.debug(f"[country] 账号地区: {country} ({country_cn})")
        return {"country": country, "country_cn": country_cn}

    def query_subscription(self) -> dict:
        """查询账号订阅状态 (免费/Ultra)

        访问 https://myaccount.google.com/subscriptions 页面并解析 HTML。
        页面为服务端渲染, 无 batchexecute RPC。

        返回: {'status': 'free'|'ultra', 'title': '订阅名称'}
        """
        try:
            resp = self.client.get(f"{BASE_URL}/subscriptions")
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[subscription] 获取订阅页面失败: {e}")
            return {"status": "free", "title": ""}

        html = resp.text
        status = "free"
        title = ""
        renew_date = ""

        # Ultra 特征: 页面含 "AI Ultra"
        if "AI Ultra" in html:
            status = "ultra"
            # 提取具体计划名, 如 "Google AI Ultra (30 TB)"
            m = re.search(r'class="SeZS9d"[^>]*>([^<]*AI Ultra[^<]*)<', html)
            title = m.group(1).strip() if m else "Google One AI Ultra"
            # 提取续期日期, 如 "Renews on Mar 23, 2026" → "2026年3月23日"
            m = re.search(r'Renews on ([A-Za-z]+ \d{1,2}, \d{4})', html)
            if m:
                from datetime import datetime as _dt
                try:
                    d = _dt.strptime(m.group(1), "%b %d, %Y")
                    renew_date = f"{d.year}年{d.month}月{d.day}日"
                except ValueError:
                    renew_date = m.group(1)

        return {"status": status, "title": title, "renew_date": renew_date}

    def query_members(self) -> dict:
        """查询成员列表 (V2esPe)

        pending 判断逻辑 (基于实测):
          - m[1] 只区分管理员(1) vs 非管理员(3), 无法区分已接受/待接受
          - pending 真正标志: m[2]==True (布尔) 且 m[9] 包含邀请数据
          - 已接受成员: len(m)=19, 无 m[2], 无 m[9]
          - 待接受成员: len(m)=10, m[2]=True, m[9]=[invite_id, null, email, ...]
        """
        raw_result = self._rpc("V2esPe", "[]")
        data = raw_result["parsed"]
        no_family = {
            "has_family": False,
            "members": [],
            "member_count": 0,
            "current_user_id": data[2] if data else None,
            "is_admin": False,
            "family_group_id": None,
            "remaining_slots": 0,
        }
        if data is None:
            return no_family
        if not isinstance(data[0], list) or data[0][1] is None:
            return no_family

        members = []
        for m in data[0][1]:
            info = m[0]
            # pending 判断: m[2]==True 或 m[9] 存在邀请数据
            is_pending = (len(m) > 2 and m[2] is True) or (len(m) > 9 and m[9] is not None)
            role = m[1]
            if role == ROLE_ADMIN:
                role_name = "admin"
            elif is_pending:
                role_name = "pending"
            else:
                role_name = "member"
            # email 来源: 已接受成员在 info[5], pending 成员在 m[9][2]
            email = info[5] if len(info) > 5 and info[5] else None
            invitation_id = None
            if is_pending and len(m) > 9 and isinstance(m[9], list):
                if len(m[9]) > 0 and m[9][0] is not None:
                    invitation_id = str(m[9][0])
                if not email and len(m[9]) > 2:
                    email = m[9][2]
            members.append({
                "name": info[0],
                "user_id": info[1],
                "avatar_url": info[2] if len(info) > 2 else None,
                "email": email,
                "role": role,
                "role_name": role_name,
                "pending": is_pending,
                "invitation_id": invitation_id,
            })

        return {
            "has_family": True,
            "members": members,
            "member_count": sum(1 for m in members if not m["pending"]),
            "current_user_id": data[2],
            "is_admin": bool(data[4]),
            "family_group_id": data[0][8] if len(data[0]) > 8 else None,
            "remaining_slots": data[3],
        }

    def create_family(self) -> bool:
        """创建家庭组 (nKULBd → Wffnob → c5gch)"""
        path = "/family/createconfirmation"

        self._rpc("nKULBd", "[]", path, seq="1")

        r = self._rpc("Wffnob", '[[null,null,["v2",18,null,["googleaccount"]]]]', path)
        raw = r["raw"].replace('\\"', '"').replace("\\\\", "\\")
        m = re.search(r"AP[A-Za-z0-9+/=_-]{20,}", raw)
        if not m:
            raise RPCError("Wffnob", r["status_code"], "无法提取加密 token")
        token = m.group(0)

        payload = json.dumps([[None, None, ["v2", 18, None, ["googleaccount"]]], [token]])
        self._rpc("c5gch", payload, path)

        return self.query_status()["has_family"]

    def send_invite(self, email: str) -> dict:
        """发送家庭组邀请 (B3vhdd → xN05r)"""
        path = "/family/invitemembers"

        self._rpc("B3vhdd", '[[null,null,["v2",18,null,["googleaccount"]]]]', path)

        payload = json.dumps([
            [None, None, ["v2", 18, None, ["googleaccount"]]],
            [[None, [email], None, 3, None, None, None, None, None, 1, email]],
        ])
        r = self._rpc("xN05r", payload, path)

        invitation_id = None
        if r["parsed"] and isinstance(r["parsed"], list) and len(r["parsed"]) > 1:
            try:
                invitation_id = r["parsed"][1][0][0]
            except (IndexError, TypeError):
                pass

        return {"success": r["status_code"] == 200, "invitation_id": invitation_id}

    def accept_invite(self) -> dict:
        """接受待处理的家庭组邀请 (SZ903d)"""
        resp = self.client.get(f"{BASE_URL}/family/pendinginvitations")
        html = resp.text

        # Google 会用 HTML 实体编码 URL (&#47; = /), 先解码再匹配
        import html as html_mod
        decoded = html_mod.unescape(html)

        token = None
        m = re.search(r"families\.google\.com/join/promo/t/([A-Za-z0-9_-]+)", decoded)
        if m:
            token = m.group(1)
        if not token:
            m = re.search(r"/family/join/t/([A-Za-z0-9_-]+)", decoded)
            if m:
                token = m.group(1)

        if not token:
            raise NoInvitationError("pendinginvitations 页面未找到邀请链接")

        join_path = f"/family/join/t/{token}"
        self.refresh_tokens(join_path)

        payload = json.dumps([
            [None, None, ["v2", 18, None, ["googleaccount"]]],
            None, None, None,
            token,
        ])
        r = self._rpc("SZ903d", payload, join_path)

        logger.debug(f"[accept_invite] SZ903d parsed={r['parsed']}")

        family_group_id = None
        if r["parsed"] and isinstance(r["parsed"], list) and len(r["parsed"]) > 1:
            try:
                family_group_id = r["parsed"][1][0][0]
            except (IndexError, TypeError):
                pass

        # HTTP 200 但无 family_group_id 说明加入失败 (地区不同、账号受限等)
        if r["status_code"] == 200 and not family_group_id:
            return {"success": False, "family_group_id": None,
                    "error": "加入失败, 可能与管理员不在同一国家/地区"}

        return {"success": r["status_code"] == 200 and bool(family_group_id),
                "family_group_id": family_group_id}

    # ── 需要 rapt token 的操作 ──

    def cancel_invite(self, invitation_id: str) -> bool:
        """撤销待接受的邀请 (fijTGe) — 管理员操作, 不需要 rapt

        Args:
            invitation_id: 邀请 ID (从 send_invite 返回或 query_members 的 pending 成员数据中获取)
        """
        path = f"/family/member/i/{invitation_id}"
        self.refresh_tokens(path)

        payload = json.dumps([
            [None, None, ["v2", 18, None, ["googleaccount"]]],
            invitation_id,
        ])
        r = self._rpc("fijTGe", payload, path)
        ok = r["status_code"] == 200
        logger.info(f"[cancel_invite] invitation_id={invitation_id}, HTTP={r['status_code']}, parsed={r['parsed']}")
        return ok

    def remove_member(self, member_user_id: str, rapt: str) -> bool:
        """移除家庭组成员 (Csu7b) — 管理员操作"""
        payload = json.dumps([
            [None, None, ["v2", 18, None, ["googleaccount"]]],
            member_user_id,
        ])
        r = self._rpc("Csu7b", payload, f"/family/remove/g/{member_user_id}", rapt=rapt)
        return r["status_code"] == 200

    def leave_family(self, rapt: str) -> bool:
        """退出家庭组 (Csu7b + "me") — 普通成员操作"""
        payload = json.dumps([
            [None, None, ["v2", 18, None, ["googleaccount"]]],
            "me",
        ])
        r = self._rpc("Csu7b", payload, "/family/leave", rapt=rapt)
        return r["status_code"] == 200

    def delete_family(self, rapt: str) -> bool:
        """删除家庭组 (hQih3e) — 管理员操作"""
        r = self._rpc("hQih3e", "[]", "/family/delete", rapt=rapt)
        return r["status_code"] == 200

    # ── 生命周期 ──

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
