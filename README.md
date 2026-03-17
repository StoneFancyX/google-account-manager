# Google Account Manager

批量管理 Google 账号的 Web 系统，支持自动登录、家庭组自动化操作、订阅状态检测。

## 功能

- **账号管理** — 邮箱 / 密码 / 辅助邮箱 / 2FA 密钥存储，实时生成 TOTP 验证码
- **分组管理** — 主号 + 子号体系，卡片式分组视图
- **自动化操作** — 基于 DrissionPage 浏览器自动化 + httpx RPC
  - 一键登录 Google 账号（密码 + 2FA）
  - 创建 / 删除家庭组
  - 发送 / 接受家庭组邀请
  - 移除 / 替换家庭组成员
  - 同步家庭组状态（Cookies 过期自动登录刷新）
- **订阅检测** — 自动识别 Google One AI Ultra 订阅状态及到期日，主号 Ultra 自动传播给组内子号
- **WebSocket 实时推送** — 自动化步骤进度实时反馈
- **调试模式** — 开启后每个自动化步骤自动截图 + 保存页面源码

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · SQLAlchemy · PostgreSQL |
| 前端 | React 19 · TypeScript · Ant Design 6 · Vite 7 |
| 浏览器自动化 | DrissionPage（登录 / 密码重验证） |
| HTTP RPC | httpx（Google 家庭组 batchexecute 接口） |
| 认证 | JWT (python-jose) · bcrypt |

## 项目结构

```
backend/
├── app.py                     # FastAPI 入口
├── config.py                  # 配置项 (环境变量)
├── run.py                     # 启动脚本
├── models/
│   ├── database.py            # SQLAlchemy 引擎
│   └── orm.py                 # ORM 模型
├── routers/
│   ├── auth.py                # 认证
│   ├── accounts.py            # 账号管理
│   ├── groups.py              # 分组管理
│   ├── dashboard.py           # 仪表盘
│   ├── browser.py             # 浏览器配置
│   ├── automation.py          # 自动化 (REST + WebSocket)
│   └── settings.py            # 系统设置
└── services/
    ├── automation.py           # 自动化核心逻辑
    ├── browser.py              # DrissionPage 浏览器管理
    ├── family_api.py           # Google 家庭组 RPC 封装
    └── account.py              # 账号业务逻辑

frontend/src/
├── api/                       # Axios 请求封装
├── pages/
│   ├── DashboardPage.tsx      # 仪表盘
│   ├── AccountsPage.tsx       # 账号管理
│   ├── GroupManage.tsx         # 分组管理
│   ├── GroupDetail.tsx         # 分组详情
│   └── SettingsPage.tsx       # 系统设置
└── layouts/
    └── MainLayout.tsx         # 主布局
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL
- Chrome / Chromium（DrissionPage 需要）

### 后端

```bash
cd backend

# 安装依赖
uv sync

# 配置环境变量 (可选，有默认值)
export GAM_DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/gam"
export GAM_SECRET_KEY="your-secret-key"

# 启动服务
uv run python run.py

# 开发模式 (热重载)
uv run python run.py --reload
```

API 文档：http://localhost:8000/docs

### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

访问：http://localhost:5173

### 生产构建

```bash
cd frontend
pnpm build
# 产物在 dist/ 目录
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

## 注意事项

- 首次登录需设置主密码，请妥善保管
- 定期备份 PostgreSQL 数据
- 自动化操作依赖 Chrome 浏览器，服务器部署需安装 Chromium
- Google 登录不支持无头模式（会被 Google 反检测拦截），服务器环境需配合 Xvfb 虚拟显示
