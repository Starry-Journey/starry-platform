# Layer 2 部署状态

## 已上线（VPS 127.0.0.1:8891，nginx `/v1/`）

- `GET /v1/healthz`、`/v1/readyz`
- `POST /v1/auth/device` 设备令牌
- `GET/POST /v1/comments`、`DELETE /v1/comments/{id}`（管理员）
- `POST /v1/chat/stream` SSE（DeepSeek，每日 20 条/设备）
- `POST /v1/charts`、`GET/DELETE /v1/charts/{id}`（Swiss Ephemeris，出生数据加密，90 天）

## 前端

- 评论区已切到 `/v1/comments`
- AI 助手已切到 `/v1/chat/stream`（SSE 流式）
- 分支：`feat/layer2`，待 PR 合并

## 验证

```bash
curl https://starryjourney.duckdns.org:8443/v1/healthz
TOKEN=$(curl -s -X POST https://starryjourney.duckdns.org:8443/v1/auth/device | jq -r .token)
curl -N -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"你好"}' https://starryjourney.duckdns.org:8443/v1/chat/stream
```

## 环境变量（/etc/starry/env）

`DATABASE_URL`、`ADMIN_TOKEN`、`CHART_ENC_KEY`、`DEEPSEEK_API_KEY`、`DAILY_MESSAGE_LIMIT`
