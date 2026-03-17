# Google Account Manager - 项目上下文

## 项目概述

Google 账号批量管理系统：FastAPI 后端 + React (Ant Design) 前端 + DrissionPage 浏览器自动化 + httpx RPC 家庭组操作。

## 技术栈

- **后端**: Python 3.11+ · FastAPI · SQLAlchemy · PostgreSQL
- **前端**: React 19 · TypeScript · Ant Design 6 · Vite 7
- **浏览器自动化**: DrissionPage（登录 / 密码重验证 / rapt 获取）
- **HTTP RPC**: httpx（Google Family batchexecute 接口）
- **认证**: JWT (python-jose) · bcrypt
- **包管理**: 后端 uv · 前端 pnpm

## 项目结构

```
backend/
├── app.py                      # FastAPI 入口，注册所有路由
├── config.py                   # 配置项 (JWT, 数据库, CORS, 服务器)
├── deps.py                     # 依赖注入 (JWT 验证, AppState)
├── run.py                      # 启动入口: uv run python run.py [--reload]
├── models/
│   ├── database.py             # SQLAlchemy 引擎 + SessionLocal
│   ├── orm.py                  # ORM 模型 (Account, Group, Config, BrowserProfile)
│   └── schemas.py              # Pydantic 请求/响应模型
├── routers/
│   ├── auth.py                 # 认证 API (登录/设置密码)
│   ├── accounts.py             # 账号管理 API (CRUD + 导入)
│   ├── groups.py               # 分组管理 API (CRUD + 成员管理)
│   ├── dashboard.py            # 仪表盘 API (统计数据)
│   ├── browser.py              # 浏览器配置 API (启动/停止/状态)
│   ├── automation.py           # 自动化 API (REST + WebSocket 实时步骤推送)
│   └── settings.py             # 系统设置 API (GET/PUT, 存 config 表)
├── services/
│   ├── account.py              # 账号 CRUD 服务
│   ├── auth.py                 # 认证服务 (密码设置/验证)
│   ├── automation.py           # 自动化核心逻辑 (StepTracker + 所有自动化函数)
│   ├── browser.py              # DrissionPage 浏览器管理 (登录 + rapt 获取)
│   ├── family_api.py           # Google Family batchexecute RPC 封装 (纯 httpx)
│   ├── group.py                # 分组 CRUD + 成员管理服务
│   └── verification.py         # 验证链接提取
└── utils/
    └── crypto.py               # 加密工具

frontend/src/
├── api/
│   ├── client.ts               # Axios 客户端 (baseURL, 拦截器)
│   ├── index.ts                # 统一导出
│   ├── accounts.ts             # 账号 API
│   ├── groups.ts               # 分组 API
│   ├── auth.ts                 # 认证 API
│   ├── dashboard.ts            # 仪表盘 API
│   ├── browser.ts              # 浏览器管理 API
│   ├── automation.ts           # 自动化 API
│   └── settings.ts             # 设置 API
├── pages/
│   ├── LoginPage.tsx            # 登录页
│   ├── DashboardPage.tsx        # 仪表盘
│   ├── AccountsPage.tsx         # 账号管理 (表格 + 操作面板)
│   ├── GroupManage.tsx           # 分组管理 (卡片列表)
│   ├── GroupDetail.tsx           # 分组详情 (成员管理)
│   └── SettingsPage.tsx         # 系统设置 (调试模式 / 无头模式)
├── components/
│   ├── AccountModal.tsx         # 账号编辑弹窗
│   ├── BrowserProfileModal.tsx  # 浏览器配置弹窗
│   ├── OperationPanel.tsx       # 自动化操作面板 (WebSocket 步骤追踪)
│   └── TOTPDisplay.tsx          # TOTP 验证码显示 + 倒计时
├── layouts/
│   └── MainLayout.tsx           # 主布局 (侧边栏 + 内容区)
├── types/
│   └── index.ts                 # TypeScript 类型定义
└── utils/
    └── mask.ts                  # 邮箱脱敏工具
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GAM_DATABASE_URL` | `postgresql://root:123456@127.0.0.1:5432/gam` | 数据库连接串 |
| `GAM_SECRET_KEY` | 随机生成 | JWT 签名密钥 |
| `GAM_TOKEN_EXPIRE_MINUTES` | `480` | Token 有效期（分钟） |
| `GAM_CORS_ORIGINS` | `http://localhost:5173` | CORS 允许的源，逗号分隔 |
| `GAM_HOST` | `127.0.0.1` | 服务监听地址 |
| `GAM_PORT` | `8000` | 服务监听端口 |

---

## 自动化架构

### 整体架构

浏览器 (DrissionPage) 只负责两件事:
1. **登录** → 提取 cookies
2. **密码/TOTP 重验证** → 获取 rapt token

家庭组的所有实际操作通过 **httpx + batchexecute RPC** 完成，不需要浏览器页面交互。

### 同步流程 (discover)

cookies 过期时的自动恢复机制 (4 级回退):

```
1. 数据库保存的 cookies → 直接查询 (最快)
   ↓ 过期
2. 运行中浏览器的 cookies → 重试
   ↓ 也过期或浏览器未运行
3. 自动启动浏览器 → 登录 → 获取新 cookies → 查询 → 关闭浏览器
   ↓ 登录失败
4. 报错提示
```

> **注意**: 自动登录强制 `headless=False`，因为 Google 会拦截无头模式登录。服务器环境需配合 Xvfb。

### StepTracker 日志追踪器

- 记录每个自动化步骤的状态 (ok / fail / skip / info)
- 支持 `on_step` 回调，通过 WebSocket 实时推送步骤进度
- `debug_mode=True` 时输出详细日志
- 设置存储在数据库 `config` 表

### 自动化函数

| 函数 | 说明 | 方式 |
|------|------|------|
| `auto_login_sync()` | 自动登录 Google 账号 | DrissionPage |
| `create_family_group_sync()` | 创建家庭组 | RPC: nKULBd → Wffnob → c5gch |
| `send_family_invite_sync()` | 发送家庭组邀请 | RPC: B3vhdd → xN05r |
| `accept_family_invite_sync()` | 接受家庭组邀请 | RPC: SZ903d |
| `remove_family_member_sync()` | 移除家庭组成员 | rapt + RPC: Csu7b |
| `leave_family_group_sync()` | 退出/删除家庭组 | rapt + RPC: Csu7b / hQih3e |
| `discover_family_group_sync()` | 发现家庭组关系 | RPC: V2esPe |
| `discover_family_by_cookies()` | 纯 cookies 发现 + 自动登录刷新 | httpx + DrissionPage 回退 |

每个函数都有对应的异步包装器 `run_xxx()` 用于 API 调用。

### 浏览器管理 (services/browser.py)

- `BrowserManager.launch(profile, headless=None)` — 启动浏览器实例，`headless` 参数可覆盖全局设置
- `login_sync()` — 同步登录 (邮箱 → 密码 → 2FA)
- `handle_reauth_sync()` — 密码 + TOTP 重验证
- `get_rapt_sync()` — 导航敏感页面获取 rapt token
- `get_cookies()` — 提取 Google 域 cookies (优先 myaccount > accounts > .google.com)

### 家庭组 RPC (services/family_api.py)

`FamilyAPI` 类封装所有 Google Family batchexecute RPC:

**纯 HTTP 操作 (只需 cookies):**
- `query_status()` — 查询家庭组状态 (DmVhMc)
- `query_members()` — 查询成员列表 (V2esPe)
- `query_subscription()` — 查询订阅状态 (HTTP GET /subscriptions 页面)
- `create_family()` — 创建家庭组 (nKULBd → Wffnob → c5gch)
- `send_invite(email)` — 发送邀请 (B3vhdd → xN05r)
- `accept_invite()` — 接受邀请 (SZ903d)

**需要 rapt token 的操作:**
- `remove_member(member_user_id, rapt)` — 移除成员 (Csu7b)
- `leave_family(rapt)` — 退出家庭组 (Csu7b + "me")
- `delete_family(rapt)` — 删除家庭组 (hQih3e)

### 订阅状态检测

- **检测方式**: HTTP GET 访问 `/subscriptions` 页面，搜索 "AI Ultra" 关键词
- **日期提取**: 正则匹配 `Renews on Mar 23, 2026` → 转换为 `2026年3月23日`
- **状态传播**: 主号 Ultra → 自动传播给同组所有子号
- **状态清理**: 成员被移除/退出/家庭组删除 → 清除订阅状态

---

## Google 家庭组操作研究成果

### 页面流程 (已用 RPC 替代，仅供参考)

| 操作 | 页面流程 | 直接 URL |
|------|---------|---------|
| 创建家庭组 | details → create → confirm → invitemembers → skip → done | — |
| 发送邀请 | invitemembers → combobox 输入 → chip → Send | `family/invitemembers` |
| 接受邀请 | details → pendinginvitations → join/t/{token} → success | `family/pendinginvitations` |
| 成员退出 | details → Leave → 密码验证 → 确认 | `family/leave` |
| 管理员删除 | details → Delete → 密码+2FA → 确认 | `family/delete` |
| 管理员移除 | details → member/{id} → Remove → 密码验证 → 确认 | `family/remove/g/{id}` |

### rapt token 机制

- 敏感操作 (leave/delete/remove) 触发密码重验证
- 验证通过后 URL 附带 `?rapt=xxx` 参数
- rapt token **跨操作共享**: 一次验证后 remove/delete/leave 全部跳过
- token 有时效性 (几分钟内有效)

### 家庭组限制

- 最多 5 成员 (管理员 + 4 名额)
- 成员 12 个月内只能切换一次家庭组

---

## 系统设置

存储在数据库 `config` 表 (key-value)，通过 `settings.py` API 读写。

| 设置项 | 说明 |
|--------|------|
| `debug_mode` | 调试模式: 自动化步骤详细日志 |
| `headless_mode` | 无头浏览器模式 (Google 登录不支持，自动登录时强制关闭) |

## 开发指引

- 后端启动: `cd backend && uv run python run.py --reload`
- 前端启动: `cd frontend && pnpm dev`
- API 文档: http://localhost:8000/docs
- 前端地址: http://localhost:5173
