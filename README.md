# starry-platform

Starry Journey 的服务端与运维代码：新闻雷达、AI 助手、备份与基础设施。

## 目录

```
apps/news-radar/   外网资讯抓取 + DeepSeek 打分 + 生成简报
apps/chatbot/      博客 AI 助手后端（DeepSeek）
apps/api/          统一后端（FastAPI：评论 / 聊天 SSE）
apps/backup/       服务器状态备份脚本与 systemd 单元
infra/             基础设施即代码（规划中）
```

## 开发

```bash
cd apps/news-radar && pip install -r requirements.txt -r requirements-dev.txt
ruff check . && pytest -q

cd apps/chatbot && pip install -r requirements.txt -r requirements-dev.txt
ruff check . && pytest -q
```

## 部署

- 新闻雷达：`/opt/news-radar`，systemd timer 每天 08:00
- AI 助手：`/opt/chatbot`，systemd 常驻，nginx 反代 8443
- 备份：`/usr/local/bin/starry-backup.sh`，加密后推送到私有备份仓库
