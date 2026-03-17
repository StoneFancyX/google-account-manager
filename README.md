# 谷歌账号管理器 (Google Account Manager)

本地存储与自动化管理的 Google 账号 Web 系统。

## 功能特性

- 🔐 主密码保护登录（bcrypt 哈希验证），账号数据存储于 PostgreSQL 数据库
- 📧 管理 Google 账号邮箱、密码及辅助邮箱
- 🔑 存储 2FA 密钥并实时生成 TOTP 验证码
- 🏷️ 标签与分组管理（主号 + 子号体系）
- 🤖 **核心亮点**：基于 DrissionPage (浏览器自动化) + httpx RPC 的自动化操作
  - 一键自动登录 Google 账号（支持密码+2FA）
  - 自动创建 Google 家庭组
  - 自动发送与接受家庭组邀请
  - 自动管理家庭组成员（踢出、退出、删除）

## 技术栈

- **后端**: Python + FastAPI + SQLAlchemy + PostgreSQL
- **浏览器自动化**: DrissionPage (登录/密码重验证) + httpx batchexecute RPC (家庭组操作)
- **前端**: React + TypeScript + Ant Design + Vite

## 快速开始

### 后端服务

推荐使用 `uv` 进行依赖管理：

```bash
cd backend
uv sync
uv run python run.py
# 访问 http://localhost:8000/docs 查看 API 文档
```

*(环境变量请参考 `backend/.env.example`，复制为 `.env` 并配置)*

### 数据库迁移

```bash
cd backend
# 自动生成迁移脚本（修改 ORM 模型后）
uv run alembic revision --autogenerate -m "描述变更"
# 执行迁移
uv run alembic upgrade head
```
*(应用启动时会自动执行 `alembic upgrade head`，通常无需手动迁移)*

### 前端服务

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

## 自动化测试与调试

系统内置了 `StepTracker` 日志追踪器，支持通过 WebSocket 实时推送自动化步骤进度。开启调试模式后，可在控制台查看每次自动化操作的详细日志。

## 开发者指南

项目结构、自动化流程细节、Google 家庭组机制的研究成果等，请详细阅读我们的开发文档：
👉 **[项目开发指南 (CLAUDE.md)](./CLAUDE.md)**

## 注意事项

- 请妥善保管系统主密码，忘记后需要修改数据库或重置
- 定期备份 PostgreSQL 数据库数据
