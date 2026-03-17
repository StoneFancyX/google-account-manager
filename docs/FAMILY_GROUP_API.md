# Google Family Group batchexecute RPC 协议

Google 家庭组管理的 batchexecute RPC 接口文档。所有接口通过统一的 batchexecute 端点调用。

---

## 概览

### 架构

```
DrissionPage (浏览器登录) → 提取 Cookies → httpx (纯 HTTP 协议操作)
```

- **登录**: DrissionPage 浏览器模式，处理 BotGuard 等 JS 挑战
- **操作**: httpx 纯 HTTP，通过 batchexecute RPC 调用

### 操作分类

**纯 HTTP 操作 (无需浏览器):**
- `DmVhMc` — 查询家庭组状态
- `V2esPe` — 查询成员列表
- `nKULBd → Wffnob → c5gch` — 创建家庭组
- `B3vhdd → xN05r` — 发送邀请
- `SZ903d` — 接受邀请

**需要 rapt token 的操作 (浏览器做密码重验证, RPC 本身仍是纯 HTTP):**
- `Csu7b` — 移除成员
- `Csu7b` + `"me"` — 退出家庭组
- `hQih3e` — 删除家庭组

### Base URL

```
https://myaccount.google.com/_/AccountSettingsUi/data/batchexecute
```

### 认证方式

1. **Cookies**: 登录后浏览器获取的完整 Cookie 集合
2. **XSRF Token**: 从页面 HTML 提取的 `at` token，每次 POST 请求必须携带

### 必需 Cookies

| Cookie | 说明 |
|--------|------|
| `SID` | Session ID |
| `HSID` | HTTP Session ID |
| `SSID` | Secure Session ID |
| `APISID` | API Session ID |
| `SAPISID` | Secure API Session ID |
| `OSID` | OAuth Session ID |
| `__Secure-1PSID` | Secure Primary Session ID |
| `__Secure-1PAPISID` | Secure Primary API Session ID |
| `SIDCC` | Session ID Check Cookie |
| `__Secure-1PSIDCC` | Secure Primary Session ID Check |

---

## Token 提取

### `GET /family/details`

从页面 HTML 中 `WIZ_global_data` 提取以下 Token:

| Token | HTML Key | 正则表达式 | 用途 |
|-------|----------|-----------|------|
| `at` | `SNlM0e` | `"SNlM0e":"([^"]+)"` | XSRF Token (POST 必需) |
| `f.sid` | `FdrFJe` | `"FdrFJe":"([^"]+)"` | 会话 ID |
| `bl` | `cfb2h` | `"cfb2h":"([^"]+)"` | 构建标签 |

```python
import re

def extract_tokens(html: str) -> dict[str, str]:
    tokens = {}
    for key, pattern in {
        "at": r'"SNlM0e":"([^"]+)"',
        "f.sid": r'"FdrFJe":"([^"]+)"',
        "bl": r'"cfb2h":"([^"]+)"',
    }.items():
        m = re.search(pattern, html)
        if m:
            tokens[key] = m.group(1)
    return tokens
```

---

## 通用请求格式

### Request

```http
POST /_/AccountSettingsUi/data/batchexecute HTTP/1.1
Host: myaccount.google.com
Content-Type: application/x-www-form-urlencoded;charset=UTF-8
X-Same-Domain: 1
Origin: https://myaccount.google.com
Referer: https://myaccount.google.com{source_path}
```

**Query Parameters:**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `rpcids` | string | 是 | RPC 方法标识符 |
| `source-path` | string | 是 | 来源页面路径 |
| `f.sid` | string | 是 | 会话 ID (从 HTML 提取) |
| `bl` | string | 是 | 构建标签 (从 HTML 提取) |
| `hl` | string | 否 | 语言代码，默认 `en` |
| `soc-app` | int | 否 | 固定值 `1` |
| `soc-platform` | int | 否 | 固定值 `1` |
| `soc-device` | int | 否 | 固定值 `1` |
| `_reqid` | int | 否 | 请求序号 |
| `rt` | string | 否 | 返回类型，固定值 `c` |
| `rapt` | string | 否 | 敏感操作的重验证 token |

**Form Body:**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `f.req` | string | 是 | JSON 编码的 RPC 调用 `[[[rpc_id, payload, null, seq]]]` |
| `at` | string | 是 | XSRF token (从 HTML 提取) |

### Response

```
)]}'

<length>
[["wrb.fr","<RPC_ID>","<JSON_DATA>",null,null,null,"generic"]]
```

响应以 `)]}'` 前缀开头 (防 XSS)，后续每行是 `长度\n数据` 格式。

---

## API 接口

### 1. 查询家庭组状态

判断当前账号是否在一个家庭组中。

**RPC ID:** `DmVhMc`

**Request:**
```
source-path: /family/details
payload: "[]"
```

**Response (无家庭组):**
```json
[false, [[5]], null, 0, null, 13]
```

**Response (有家庭组):**
```json
[true, null, null, 5, null, 13]
```

**字段说明:**

| 索引 | 类型 | 说明 |
|------|------|------|
| `[0]` | boolean | 是否有家庭组 |
| `[1]` | array \| null | 无家庭组时为 `[[5]]`，有时为 `null` |
| `[3]` | int | 剩余邀请名额 (有家庭组时才有意义) |
| `[5]` | int | 固定值 `13` (未知用途) |

---

### 2. 查询成员列表

获取家庭组所有成员的详细信息。

**RPC ID:** `V2esPe`

**Request:**
```
source-path: /family/details
payload: "[]"
```

**Response (无家庭组):**
```json
[[null, null, 0], 0, "USER_ID", 6, false, false]
```

**Response (有家庭组):**
```json
[
  [
    null,
    [MEMBER_LIST],
    MEMBER_COUNT,
    null, null, null, null,
    [SETTINGS],
    "FAMILY_GROUP_ID"
  ],
  MEMBER_COUNT,
  "CURRENT_USER_ID",
  REMAINING_SLOTS,
  IS_ADMIN,
  false
]
```

**成员对象结构 (MEMBER_LIST 中的每个元素):**

```json
[
  [
    "显示名",           // [0][0] 全名
    "USER_ID",          // [0][1] Google User ID
    "AVATAR_URL",       // [0][2] 头像 URL
    "名",               // [0][3] First Name
    "姓",               // [0][4] Last Name
    "email@gmail.com",  // [0][5] 邮箱
    2                   // [0][6] 未知
  ],
  1,                    // [1] 角色: 1=管理员, 3=非管理员(已接受或待接受均为3)
  null,                 // [2] 待接受标志: true=pending, null/不存在=已接受
  null, null, null, null,
  "#BA68C8",            // [7] 头像背景色
  false,
  null,                 // [9] 邀请数据: pending时为 [invite_id, null, email, 2, sent_ts, expire_ts, ...]
  null, null, true, null, null,
  [false, false, false, [false, false]],
  null, null, false
]
```

**已接受成员 vs 待接受成员:**

| 字段 | 已接受成员 | 待接受成员 (pending) |
|------|-----------|---------------------|
| `m[1]` (role) | 3 (非管理员) | 3 (非管理员) |
| `m[2]` (pending flag) | null 或不存在 | `true` |
| `m[9]` (邀请数据) | null 或不存在 | `[invite_id, null, email, 2, sent_ts, expire_ts, ...]` |
| `len(m)` | 19 | 10 |

**⚠️ pending 判断逻辑 (基于实测):**

- `m[1]=3` **不代表** pending！它只表示"非管理员"
- pending 真正标志: `m[2] == True` (布尔) 且 `m[9]` 包含邀请数据
- **已接受成员邮箱**在 `m[0][5]` (即 `info[5]`)
- **待接受成员邮箱**在 `m[9][2]` (info[5] 为空)

**字段总结:**

| 路径 | 类型 | 说明 |
|------|------|------|
| `data[0][1]` | array | 成员列表 |
| `data[0][1][n][0][0]` | string | 成员全名 |
| `data[0][1][n][0][1]` | string | 成员 User ID |
| `data[0][1][n][0][2]` | string | 成员头像 URL |
| `data[0][1][n][0][5]` | string | 成员邮箱 (已接受成员) |
| `data[0][1][n][1]` | int | 角色: 1=管理员, 3=非管理员(含已接受和待接受) |
| `data[0][1][n][2]` | bool | 待接受标志: `true`=pending, `null`=已接受 |
| `data[0][1][n][9]` | array | 邀请数据 (仅 pending): `[invite_id, null, email, 2, sent_ts, expire_ts, ...]` |
| `data[0][8]` | string | 家庭组 ID |
| `data[1]` | int | 成员总数 |
| `data[2]` | string | 当前用户 ID |
| `data[3]` | int | 剩余邀请名额 |
| `data[4]` | boolean | 当前用户是否为管理员 |

---

### 3. 创建家庭组

创建新的家庭组。需要按顺序调用 3 个 RPC。

#### Step 1/3: 创建确认

**RPC ID:** `nKULBd`

**Request:**
```
source-path: /family/createconfirmation
payload: "[]"
seq: "1"
```

**Response:** HTTP 200 (无需解析)

---

#### Step 2/3: 获取加密 Token

**RPC ID:** `Wffnob`

**Request:**
```
source-path: /family/createconfirmation
payload: '[[null,null,["v2",18,null,["googleaccount"]]]]'
```

**Response:** 包含 `AP` 开头的加密 Token

**Token 提取:**
```python
clean = response_text.replace('\\"', '"').replace('\\\\', '\\')
m = re.search(r'AP[A-Za-z0-9+/=_-]{20,}', clean)
wffnob_token = m.group(0)
```

---

#### Step 3/3: 最终创建

**RPC ID:** `c5gch`

**Request:**
```
source-path: /family/createconfirmation
payload: json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    [WFFNOB_TOKEN],
])
```

**Response:** HTTP 200 = 创建成功

**验证:** 调用 `DmVhMc`，检查 `data[0]` 是否为 `true`

---

### 4. 发送家庭组邀请

发送邀请需要按顺序调用 2 个 RPC。

#### Step 1/2: 获取加密 Token

**RPC ID:** `B3vhdd`

**Request:**
```
source-path: /family/invitemembers
payload: '[[null,null,["v2",18,null,["googleaccount"]]]]'
```

**Response:**
```json
[null, true]
```

---

#### Step 2/2: 发送邀请

**RPC ID:** `xN05r`

**Request:**
```
source-path: /family/invitemembers
payload: json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    [[None, [INVITEE_EMAIL], None, 3, None, None, None, None, None, 1, INVITEE_EMAIL]]
])
```

**Response:**
```json
[
  [["\u003ctoken\u003e", 300]],
  [["INVITATION_ID",
    ["invitee@gmail.com"],
    null, 3,
    SENT_TIMESTAMP,
    EXPIRE_TIMESTAMP,
    "googleaccount",
    null, 2, null,
    "invitee@gmail.com",
    null, null, null, 0
  ]]
]
```

**字段说明:**

| 路径 | 类型 | 说明 |
|------|------|------|
| `data[1][0][0]` | string | 邀请 ID |
| `data[1][0][1][0]` | string | 被邀请者邮箱 |
| `data[1][0][4]` | int | 发送时间戳 (ms) |
| `data[1][0][5]` | int | 过期时间戳 (ms) |

---

### 5. 接受家庭组邀请

被邀请者接受邀请。需要先从 pendinginvitations 页面提取邀请 token。

#### 提取邀请 Token

```
GET /family/pendinginvitations
```

从页面 HTML 中提取邀请链接:
- 正则 1: `families\.google\.com/join/promo/t/([A-Za-z0-9_-]+)`
- 正则 2 (备选): `/family/join/t/([A-Za-z0-9_-]+)`

#### 接受邀请

**RPC ID:** `SZ903d`

**Request:**
```
source-path: /family/join/t/{INVITE_TOKEN}
payload: json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    None, None, None,
    INVITE_TOKEN
])
```

**注意:** 发送前需要先对 `/family/join/t/{INVITE_TOKEN}` 路径重新刷新 tokens (at, f.sid, bl)。

**Response:** 包含家庭组信息

```json
[null, [
  ["FAMILY_GROUP_ID", "ADMIN_USER_ID",
    ["管理员名字", null, "头像URL", "邮箱", "姓", "名", 1, ...],
    3, INVITE_SENT_TS, INVITE_EXPIRE_TS, "googleaccount",
    null, null,
    [[ADMIN_USER_ID, null, 1, [管理员信息], 1, "Family manager & parent"]],
    "INVITE_TOKEN"
  ],
  2, false
]]
```

| 路径 | 说明 |
|------|------|
| `data[1][0][0]` | 家庭组 ID |

---

### 6. 移除家庭组成员

管理员移除指定成员。

**前置条件:**
- 当前用户必须是管理员
- 需要通过密码/TOTP 重验证获取 `rapt` token

**RPC ID:** `Csu7b`

**Request:**
```
source-path: /family/remove/g/{MEMBER_USER_ID}
payload: json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    MEMBER_USER_ID
])
rapt: 通过 URL 查询参数传递
```

**Response:**
```json
[[["\u003ctoken\u003e", 300]]]
```
HTTP 200 = 移除成功

**验证:** 调用 `V2esPe` 检查成员列表

---

### 7. 成员退出家庭组

普通成员主动退出家庭组。复用 `Csu7b` RPC，用 `"me"` 作为成员 ID。

**前置条件:**
- 当前用户必须是普通成员 (非管理员)
- 需要通过密码重验证获取 `rapt` token
- 成员退出通常只需密码验证，**不需要 TOTP**

**RPC ID:** `Csu7b` (与移除成员相同)

**Request:**
```
source-path: /family/leave
payload: json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    "me"
])
rapt: 通过 URL 查询参数传递
```

**与移除成员的区别:**

| | 移除成员 (Remove) | 退出家庭组 (Leave) |
|---|---|---|
| 操作者 | 管理员 | 普通成员 |
| RPC ID | `Csu7b` | `Csu7b` (相同) |
| payload 中的 ID | 目标成员 User ID | `"me"` |
| source-path | `/family/remove/g/{id}` | `/family/leave` |
| 验证要求 | 密码 + 可能 TOTP | 仅密码 |

**Response:**
```json
[[["\u003ctoken\u003e", 300]]]
```
HTTP 200 = 退出成功

**验证:** 调用 `DmVhMc`，检查 `data[0]` 是否为 `false`

---

### 8. 删除家庭组

管理员删除整个家庭组。

**前置条件:**
- 当前用户必须是管理员
- 需要通过密码 + TOTP 重验证获取 `rapt` token

**RPC ID:** `hQih3e`

**Request:**
```
source-path: /family/delete
payload: "[]"
rapt: 通过 URL 查询参数传递
```

**Response:** HTTP 200 = 删除成功

**验证:** 调用 `DmVhMc`，检查 `data[0]` 是否为 `false`

---

## 操作速查表

| 操作 | RPC ID | source-path | payload 关键内容 | 验证要求 |
|------|--------|-------------|-----------------|---------|
| 查询状态 | `DmVhMc` | `/family/details` | `[]` | 无 |
| 查询成员 | `V2esPe` | `/family/details` | `[]` | 无 |
| 创建家庭组 | `nKULBd → Wffnob → c5gch` | `/family/createconfirmation` | 3 步 | 无 |
| 发送邀请 | `B3vhdd → xN05r` | `/family/invitemembers` | 含邮箱 | 无 |
| 接受邀请 | `SZ903d` | `/family/join/t/{token}` | 含 invite token | 无 |
| 移除成员 | `Csu7b` | `/family/remove/g/{id}` | 含 user_id | rapt (密码+可能TOTP) |
| 成员退出 | `Csu7b` | `/family/leave` | `"me"` | rapt (仅密码) |
| 删除家庭组 | `hQih3e` | `/family/delete` | `[]` | rapt (密码+可能TOTP) |

---

## rapt token 机制

- 敏感操作 (remove / leave / delete) 触发浏览器密码重验证
- 验证通过后 URL 附带 `?rapt=xxx` 参数
- rapt token **跨操作共享**: 一次验证后 remove/delete/leave 全部跳过
- token 有时效性 (几分钟内有效)

---

## 响应解析

```python
import json

def parse_response(text: str, rpc_id: str):
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
```

---

## 完整调用示例

```python
import json
import re
from urllib.parse import urlencode
import httpx

# 1. 获取 tokens
resp = client.get("https://myaccount.google.com/family/details")
tokens = extract_tokens(resp.text)

# 2. 查询家庭组状态
result = batchexecute(client, tokens, "DmVhMc", "[]")
has_family = result["parsed"][0]  # True / False

# 3. 查询成员列表
result = batchexecute(client, tokens, "V2esPe", "[]")
members = result["parsed"][0][1]  # 成员数组

# 4. 创建家庭组 (3步)
batchexecute(client, tokens, "nKULBd", "[]", "/family/createconfirmation")
resp = batchexecute(client, tokens, "Wffnob",
    '[[null,null,["v2",18,null,["googleaccount"]]]]',
    "/family/createconfirmation")
token = re.search(r'AP[A-Za-z0-9+/=_-]{20,}', resp["raw"]).group(0)
payload = json.dumps([[None, None, ["v2", 18, None, ["googleaccount"]]], [token]])
batchexecute(client, tokens, "c5gch", payload, "/family/createconfirmation")

# 5. 发送邀请 (2步)
batchexecute(client, tokens, "B3vhdd",
    '[[null,null,["v2",18,null,["googleaccount"]]]]',
    "/family/invitemembers")
invite_payload = json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    [[None, ["invitee@gmail.com"], None, 3, None, None, None, None, None, 1, "invitee@gmail.com"]]
])
batchexecute(client, tokens, "xN05r", invite_payload, "/family/invitemembers")

# 6. 接受邀请 (先提取 token, 再 RPC)
resp = client.get("https://myaccount.google.com/family/pendinginvitations")
token = re.search(r'/family/join/t/([A-Za-z0-9_-]+)', resp.text).group(1)
# 重新刷新 tokens
tokens = extract_tokens(client.get(f"https://myaccount.google.com/family/join/t/{token}").text)
accept_payload = json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    None, None, None, token
])
batchexecute(client, tokens, "SZ903d", accept_payload, f"/family/join/t/{token}")

# 7. 移除成员 (需要 rapt token)
remove_payload = json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    "MEMBER_USER_ID"
])
batchexecute(client, tokens, "Csu7b", remove_payload, "/family/remove/g/MEMBER_USER_ID", rapt=RAPT_TOKEN)

# 8. 成员退出家庭组 (需要 rapt token)
leave_payload = json.dumps([
    [None, None, ["v2", 18, None, ["googleaccount"]]],
    "me"
])
batchexecute(client, tokens, "Csu7b", leave_payload, "/family/leave", rapt=RAPT_TOKEN)

# 9. 管理员删除家庭组 (需要 rapt token)
batchexecute(client, tokens, "hQih3e", "[]", "/family/delete", rapt=RAPT_TOKEN)
```

---

## 错误处理

| HTTP 状态 | 说明 |
|-----------|------|
| 200 | 成功 |
| 400 | 请求格式错误 (检查 payload 格式) |
| 401 | 认证失败 (Cookies 过期或缺失) |
| 403 | XSRF token 无效 (重新获取 `at` token) |

### 异常类型

| 异常 | 说明 |
|------|------|
| `TokenError` | 页面 token (at/f.sid/bl) 提取失败 |
| `RPCError` | batchexecute RPC 调用失败 (含 rpc_id 和 status_code) |
| `NoInvitationError` | pendinginvitations 页面未找到邀请链接 |

---

## 登录流程 (DrissionPage)

```python
from DrissionPage import WebPage, ChromiumOptions

co = ChromiumOptions()
co.set_argument("--lang", "en-US")
page = WebPage(chromium_options=co)

# 1. 打开登录页
page.get("https://accounts.google.com/signin")

# 2. 输入邮箱
page.ele("#identifierId", timeout=10).input(email)
page.ele("#identifierNext", timeout=5).click()

# 3. 输入密码 (注意等待 CSS 过渡动画)
time.sleep(2)
page.ele("@name=Passwd", timeout=15).input(password)
page.ele("#passwordNext", timeout=5).click()

# 4. TOTP 验证 (如果需要)
if "challenge" in page.url:
    code = pyotp.TOTP(totp_secret).now()
    page.ele("#totpPin", timeout=10).input(code)
    page.ele("#totpNext", timeout=5).click()

# 5. 提取 cookies
cookies = {}
for c in page.cookies():
    cookies[c.get("name", "")] = c.get("value", "")
page.quit()
```

**注意事项:**
- 密码输入框选择器必须用 `@name=Passwd`，不能用 `input[type="password"]`
- 输入密码前需要 `time.sleep(2)` 等 Google 的 CSS 过渡动画完成
- 2FA 选择页面 (`challenge/selection`) 需先点击 "Authenticator" 选项
