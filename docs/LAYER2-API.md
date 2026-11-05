# Layer 2：统一后端 API 设计

> 目标：把现在分散的「评论 C++ 服务 + AI 助手 Python 服务 + 未来的占星」收敛成一个可维护的 API，
> 同时保持静态博客不变。本文只定接口与数据模型，代码在 `apps/api/`。

## 1. 范围

| 能力 | 现状 | Layer 2 目标 |
|---|---|---|
| AI 对话 | `chatbot` 单文件 HTTP 服务，无会话、无流式 | `/v1/chat` SSE、会话持久化、配额 |
| 评论 | C++ `chat-server`，按房间存 SQLite | `/v1/comments` 统一入口（先代理，后迁移） |
| 占星 | 无 | `/v1/charts` 星盘计算与存储 |
| 搜索 | 无 | `/v1/search`（Phase 2） |
| 认证 | 无 | 设备令牌 + 邮箱魔法链接（可选 GitHub OAuth） |

**非目标**：不做微服务、不上 Kubernetes、不重写博客前端。

## 2. 技术选型

- **Python 3.11 + FastAPI + Uvicorn**：异步、原生 OpenAPI、SSE 方便；与现有 Python 服务一致
- **Pydantic v2**：请求/响应模型与校验
- **SQLAlchemy 2 + Alembic**：迁移可追踪
- **SQLite（开发/单机）→ Postgres（多用户）**：先用 SQLite，接口层不写死方言
- **httpx**：调用 DeepSeek 与代理评论服务
- **pyswisseph**：星盘计算（注意 AGPL，见 §8）

## 3. 目录

```
apps/api/
├── app/
│   ├── main.py            # FastAPI 实例、中间件、路由注册
│   ├── config.py          # pydantic-settings，读 /etc/starry/env
│   ├── db.py              # engine/session
│   ├── models.py          # SQLAlchemy 模型
│   ├── schemas.py         # Pydantic 模型
│   ├── deps.py            # 认证、限流依赖
│   └── routers/
│       ├── health.py
│       ├── auth.py
│       ├── chat.py
│       ├── comments.py
│       └── charts.py
├── alembic/
├── tests/
└── pyproject.toml
```

## 4. 通用约定

- 版本前缀 `/v1`；破坏性变更升 `/v2`
- 错误统一：
  ```json
  { "error": { "code": "rate_limited", "message": "慢一点呀", "request_id": "..." } }
  ```
- 认证：`Authorization: Bearer <token>`
- 分页：`?limit=20&cursor=...`，返回 `next_cursor`
- 幂等：写接口支持 `Idempotency-Key` 头（30 分钟缓存）
- CORS：只允许 `https://starry-journey.github.io` 与本地端口
- 请求 ID：`X-Request-ID`，日志贯穿

## 5. 认证

### 5.1 流程

1. `POST /v1/auth/device` → 返回匿名设备令牌（用于评论/试用）
2. `POST /v1/auth/magic-link` `{email}` → 发邮件（Resend/SMTP）
3. `GET /v1/auth/verify?token=` → 返回会话 JWT（7 天）+ refresh（30 天）
4. `POST /v1/auth/refresh`、`POST /v1/auth/logout`

### 5.2 规则

- 匿名设备：每天 20 条聊天、评论需填昵称
- 登录用户：每天 200 条聊天；占星需要登录
- 令牌只存哈希；JWT 密钥在 `/etc/starry/env`

## 6. 聊天 API

### 6.1 流式

`POST /v1/chat/stream`（SSE）

```json
{ "conversation_id": "c_123", "message": "介绍一下木星" }
```

响应：

```
event: meta
data: {"conversation_id":"c_123","message_id":"m_1"}

event: delta
data: {"text":"木星是"}

event: done
data: {"usage":{"prompt":120,"completion":80},"finish":"stop"}
```

- 服务端保存 user/assistant 消息
- 上游超时 60s；客户端断开则取消上游（`asyncio.CancelledError`）
- 失败发 `event: error`，HTTP 仍 200（SSE 约定）

### 6.2 会话

- `GET /v1/conversations?limit=20`
- `GET /v1/conversations/{id}/messages?limit=50&cursor=`
- `DELETE /v1/conversations/{id}`
- `PATCH /v1/conversations/{id}` 改标题

### 6.3 配额

- `usage(user_id, date, messages, tokens)`
- 超限返回 429 + `Retry-After`

## 7. 评论 API

### 7.1 先代理，后迁移

现有 C++ 服务继续跑，FastAPI 做统一入口：

- `GET /v1/comments?room=post:abc&limit=50`
- `POST /v1/comments` `{room, content, nickname?}`
- `DELETE /v1/comments/{id}`（管理员）

内部转发到 `http://127.0.0.1:8888/api/...`，补认证/限流/审计。
评论迁移到 Postgres 放在 M4，避免一次性双写。

### 7.2 房间命名

`room = "post:" + sha1(pathname).slice(0,12)`，与前端现有规则兼容。

## 8. 占星 API

### 8.1 接口

`POST /v1/charts`（需登录）

```json
{
  "name": "starry",
  "birth_date": "2000-01-01",
  "birth_time": "08:30",
  "timezone": "Asia/Shanghai",
  "latitude": 31.23,
  "longitude": 121.47,
  "house_system": "placidus"
}
```

响应：

```json
{
  "id": "ch_1",
  "planets": [{"name":"Sun","sign":"Capricorn","degree":10.2,"house":10}],
  "houses": [{"house":1,"sign":"Aries","degree":5.1}],
  "aspects": [{"a":"Sun","b":"Moon","type":"trine","orb":1.2}],
  "created_at": "..."
}
```

- `GET /v1/charts/{id}`、`DELETE /v1/charts/{id}`
- 出生数据属于敏感信息：加密存储（Fernet），默认 90 天保留，可随时删除
- 日志不记录原始出生时间/地点

### 8.2 许可证

`pyswisseph` 是 **AGPL-3.0**。本项目代码公开（GitHub），满足 AGPL 的网络使用条款即可；
若未来闭源，需要换 MIT 的 `skyfield`（能算行星位置，但宫位需自己实现）或购买商业授权。

## 9. 数据模型

```sql
users(id, email, created_at, plan)
sessions(id, user_id, token_hash, expires_at, created_at)
conversations(id, user_id, title, created_at, updated_at)
messages(id, conversation_id, role, content, tokens, created_at)
usage(user_id, date, messages, tokens, PRIMARY KEY(user_id,date))
charts(id, user_id, encrypted_birth, chart_json, created_at, expires_at)
comments(id, room, author, content, status, created_at)  -- M4 迁移后
```

索引：`messages(conversation_id, created_at)`、`comments(room, created_at)`、`usage(user_id,date)`。

## 10. 部署

```ini
# /etc/systemd/system/starry-api.service
[Service]
WorkingDirectory=/opt/starry-api
EnvironmentFile=/etc/starry/env
ExecStart=/opt/starry-api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8891
Restart=always
```

nginx（8443）：

```nginx
location /v1/ {
    proxy_pass http://127.0.0.1:8891;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;          # SSE 必须
    proxy_read_timeout 120s;
}
location /bot/ { proxy_pass http://127.0.0.1:8890/; }   # 过渡期保留
```

迁移期：博客前端先切 `/v1/chat/stream`，`/bot` 保留一个版本后下线。

## 11. 测试

- 单元：schemas、配额、房间哈希、星盘计算（固定出生数据 → golden JSON）
- 集成：`httpx.AsyncClient` + 临时 SQLite；DeepSeek 用 `respx` mock
- 契约：OpenAPI 快照，防止前端破坏
- E2E：Playwright 打开 `/solar/` 的 AI 面板，断言 SSE 首字到达
- 安全：越权（A 读 B 的会话）、限流、超大请求

## 12. 里程碑

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 | FastAPI 骨架、`/healthz`、配置、SQLite、CI | 测试通过，服务可起 |
| M2 | 设备令牌 + 魔法链接 + `/v1/chat/stream` | 前端可流式对话 |
| M3 | 会话列表、配额、评论代理 | 评论/聊天统一域名 |
| M4 | 占星 charts + 加密 + 删除 | 星盘接口可用 |
| M5 | 评论迁移 Postgres、全文搜索 | 去 C++ 依赖 |

## 13. 风险

- AGPL：占星库许可证需与开源策略一致
- SSE 经过 nginx/Cloudflare 可能被缓冲，需要关闭 buffering
- 出生数据隐私：必须加密、可删除、不进日志
- 迁移期双入口（`/bot` 与 `/v1`）要有明确下线日期
