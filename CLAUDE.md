# Google Account Manager - 项目上下文

## 项目概述
Google 账号管理系统：FastAPI 后端 + React (Ant Design) 前端 + DrissionPage 浏览器自动化 + httpx RPC 家庭组操作。

## 技术栈
- **后端**: FastAPI, SQLAlchemy, PostgreSQL, DrissionPage (浏览器自动化), httpx (Google RPC)
- **前端**: React + TypeScript + Ant Design + Vite
- **自动化**: DrissionPage 登录/密码重验证 + httpx batchexecute RPC 家庭组操作

## 项目结构
```
backend/
  app.py                    # FastAPI 入口，注册所有路由
  config.py                 # 应用配置 (JWT, 数据库, CORS, 服务器)
  deps.py                   # 依赖注入 (AppState, CryptoManager, Service 依赖, JWT 验证)
  run.py                    # 启动入口
  models/
    database.py             # SQLAlchemy 引擎 + SessionLocal
    orm.py                  # ORM 模型 (Account, Group, Config, BrowserProfile)
    schemas.py              # Pydantic 请求/响应模型
  routers/
    auth.py                 # 认证 API
    accounts.py             # 账号管理 API
    groups.py               # 分组管理 API
    dashboard.py            # 仪表盘 API
    browser.py              # 浏览器配置文件管理 API
    automation.py           # 自动化操作 API (REST + WebSocket 实时步骤追踪)
    settings.py             # 系统设置 API (GET/PUT)
  services/
    auth.py                 # 认证服务 (密码设置/验证)
    account.py              # 账号 CRUD 服务
    group.py                # 分组 CRUD + 成员管理服务
    automation.py           # 自动化核心逻辑 (StepTracker + 所有自动化函数)
    browser.py              # DrissionPage 浏览器管理 (登录 + rapt 获取)
    family_api.py           # Google Family batchexecute RPC 封装 (纯 httpx)
    verification.py         # 邮箱/短信验证码获取服务
  utils/
    crypto.py               # 加密工具 (CryptoManager)

frontend/src/
  api/
    client.ts               # Axios 客户端
    index.ts                # 统一导出
    accounts.ts, groups.ts, auth.ts, dashboard.ts, browser.ts, automation.ts, settings.ts
  pages/
    LoginPage.tsx            # 登录页
    DashboardPage.tsx        # 仪表盘
    AccountsPage.tsx         # 账号管理
    GroupManage.tsx           # 分组管理
    GroupDetail.tsx           # 分组详情
    SettingsPage.tsx          # 系统设置 (调试模式 + 无头模式开关)
  components/
    AccountModal.tsx         # 账号编辑弹窗
    BrowserProfileModal.tsx  # 浏览器配置文件弹窗
    OperationPanel.tsx       # 自动化操作面板
    TOTPDisplay.tsx          # TOTP 验证码显示组件
  layouts/
    MainLayout.tsx           # 主布局 (侧边栏 + 内容区)
    MainLayout.css           # 主布局样式
  types/
    index.ts                 # TypeScript 类型定义
  theme/
    index.ts                 # Ant Design 主题配置
  styles/
    global.css               # 全局样式
  utils/
    mask.ts                  # 数据脱敏工具
```

## 自动化架构 (RPC 版)

### 整体架构
浏览器 (DrissionPage) 只负责两件事:
1. **登录** → 提取 cookies
2. **密码/TOTP 重验证** → 获取 rapt token

家庭组的所有实际操作 (创建/邀请/接受/移除/退出/删除) 通过 **httpx + batchexecute RPC** 完成，不再需要浏览器页面交互。

### StepTracker 日志追踪器
- 记录每个自动化步骤的状态 (ok/fail/skip/info)
- 支持 `on_step` 回调，通过 WebSocket 实时推送步骤进度
- 日志输出到 Python logging
- 通过 `_is_debug_mode()` 从数据库 config 表读取调试模式设置

### 自动化函数列表
1. `auto_login_sync(page, email, password, totp_secret, recovery_email, verification_url, on_step)` - 自动登录
2. `create_family_group_sync(page, on_step)` - 创建家庭组 (RPC: nKULBd → Wffnob → c5gch)
3. `send_family_invite_sync(page, invite_email, on_step)` - 发送家庭组邀请 (RPC: B3vhdd → xN05r)
4. `accept_family_invite_sync(page, on_step)` - 接受家庭组邀请 (RPC: SZ903d)
5. `remove_family_member_sync(page, member_email, password, totp_secret, on_step)` - 移除家庭组成员 (rapt + RPC: Csu7b)
6. `leave_family_group_sync(page, password, totp_secret, on_step)` - 退出/删除家庭组 (rapt + RPC: Csu7b/hQih3e)
7. `discover_family_group_sync(page, on_step)` - 发现家庭组关系 (RPC: V2esPe)
8. `discover_family_by_cookies(account_id, saved_cookies_json, browser_profile_id)` - 纯 cookies 发现家庭组 (不需要浏览器)

每个函数都有对应的异步包装器 `run_xxx()` 用于 API 调用。

### 浏览器管理 (backend/services/browser.py)
- `BrowserManager`: 管理所有 DrissionPage 浏览器实例生命周期
- `login_sync(page, email, password, totp_secret, recovery_email)`: 同步登录
- `handle_reauth_sync(page, password, totp_secret)`: 密码+TOTP 重验证
- `get_rapt_sync(page, target_path, password, totp_secret)`: 导航到敏感页面获取 rapt token

### 家庭组 RPC API (backend/services/family_api.py)
`FamilyAPI` 类封装了所有 Google Family batchexecute RPC:

**纯 HTTP 操作 (只需 cookies):**
- `query_status()` - 查询家庭组状态 (DmVhMc)
- `query_members()` - 查询成员列表 (V2esPe)
- `query_subscription()` - 查询订阅状态
- `create_family()` - 创建家庭组 (nKULBd → Wffnob → c5gch)
- `send_invite(email)` - 发送邀请 (B3vhdd → xN05r)
- `accept_invite()` - 接受邀请 (SZ903d)

**需要 rapt token 的操作:**
- `remove_member(member_user_id, rapt)` - 移除成员 (Csu7b)
- `leave_family(rapt)` - 退出家庭组 (Csu7b + "me")
- `delete_family(rapt)` - 删除家庭组 (hQih3e)

---

## Google 家庭组操作研究成果 (Playwright MCP 实测)

### 1. 创建家庭组 — 6步流程
```
family/details → "Get started" 按钮
  → family/create → 点击 "Create a Family Group" 链接
    → family/createconfirmation → 点击 "Confirm" 按钮
      → family/invitemembers → 点击 "Skip" 跳过邀请
        → family/invitationcomplete → 点击 "Got it"
          → 回到 family/details (创建完成)
```
- 已有家庭组时 `family/details` 直接显示成员列表

### 2. 发送邀请 — Combobox 流程
```
family/invitemembers → combobox[role] 输入框
  → 输入邮箱 → 点击下拉 option[role]
    → 邮箱变成 chip → Send 按钮启用
      → 点击 "Send" → 邀请成功
```
- 输入框是 combobox 角色，不是普通 textbox
- 输入后需选择下拉选项，邮箱才变成 chip
- 可直接导航 `family/invitemembers` URL
- 最多 5 成员 (管理员 + 4 邀请名额)

### 3. 接受邀请 — pendinginvitations 流程
```
family/details → "View invitation" 链接
  → family/pendinginvitations → 点击 "Join" 链接
    → family/join/t/{token} → "Join Family Group" 按钮
      → family/join/success/ → "Welcome to the family!"
```
- 被邀请者的 `family/details` 显示 "View invitation" 链接
- 中间经过 `family/pendinginvitations` 页面
- 加入链接含 token: `family/join/t/{token}`
- **12个月限制**: "You can only switch to another Family Group once in a 12-month period"

### 4. 成员退出 — 密码重验证
```
family/details → "Leave Family Group" 链接
  → family/leave → 可能需要密码重验证
    → 确认退出 → 退出成功
```
- 成员看到 "Leave Family Group" (区别于管理员的 "Delete")
- 第一次需要密码验证，同一会话内第二次跳过 (rapt token 缓存)
- 成员退出只需密码，**不需要 2FA/TOTP**

### 5. 管理员删除家庭组 — 密码 + 2FA
```
family/details → "Delete Family Group" 链接
  → family/delete → 密码 + 2FA 重验证
    → 确认删除 → 删除成功
```
- 管理员看到 "Delete Family Group"
- 需要**密码 + 2FA (TOTP)** 双重验证
- rapt token 有时效缓存

### 6. 管理员移除成员 — 直接 URL + 密码验证 ✅
```
family/details → 提取成员链接 href 中的 member_id
  → 直接导航 family/remove/g/{member_id} (跳过成员详情页)
    → 密码验证 (可能被 rapt 缓存跳过, 可能需要 2FA)
      → 确认页: "Remove family member?" → "Remove" 按钮
        → 状态消息: "Member removed from family group"
```
- ✅ 直接 URL `family/remove/g/{member_id}` 可跳过成员详情页的 3 步点击
- member_id 从 `family/details` 页面成员链接的 href 提取 (格式: `family/member/g/{id}`)
- 密码验证不固定: 有时只需密码, 有时需要密码+2FA
- rapt token 跨操作共享, 短时间内可跳过验证

### 直接 URL 快捷方式 (全部实测验证 ✅)
| 操作 | 直接 URL | 首次验证 | rapt 缓存后 |
|------|---------|---------|-----------|
| 发送邀请 | `family/invitemembers` | 无需 | 无需 |
| 接受邀请 | `family/pendinginvitations` | 无需 | 无需 |
| 成员退出 | `family/leave` | 仅密码 | 跳过 |
| 管理员删除 | `family/delete` | 密码+可能2FA | 跳过 |
| 管理员移除 | `family/remove/g/{id}` | 密码+可能2FA | 跳过 |

### rapt token 机制
- 敏感操作 (leave/delete/remove) 触发密码重验证
- 验证通过后 URL 附带 `?rapt=xxx` 参数
- rapt token **跨操作共享**: 一次验证后 remove/delete/leave 全部跳过
- token 有时效性 (精确时长未知, 几分钟内有效)

### Google 多账号机制
- URL 路径: `/u/0/`, `/u/1/` 区分账号
- 查询参数: `authuser=0`, `authuser=1`
- 添加账号: `accounts.google.com/AddSession`
- Cookie 在同一浏览器实例内共享

---

## 系统设置
- **后端**: `backend/routers/settings.py` 提供 GET/PUT API
- **存储**: 数据库 `config` 表 (key-value)
- **前端**: `SettingsPage.tsx` 提供开关 UI
- 支持的设置项:
  - `debug_mode`: 调试模式
  - `headless_mode`: 无头浏览器模式

## 待完成工作
1. ✅ ~~管理员移除成员流程~~: 已完成研究并更新代码
2. ✅ ~~更新 `accept_family_invite_sync`~~: 已用 RPC (SZ903d) 实现
3. ✅ ~~更新 `leave_family_group_sync`~~: 成员退出+管理员删除统一用 rapt + RPC 处理
4. ✅ ~~更新 `remove_family_member_sync`~~: rapt + RPC (Csu7b) 实现
5. ⬜ 端到端测试: 通过 DrissionPage 浏览器实测所有自动化函数
