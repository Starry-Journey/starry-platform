# content-bot

每日随笔草稿：主题轮换 + DeepSeek + 星空封面 SVG。

## 流程

```
06:30 timer
  → generate.py 生成 md + svg
  → 推 daily-YYYY-MM-DD 分支
  → GitHub Actions 开 PR（不自动合并）
  → 飞书提醒审核
```

## 环境变量

- `DAILY_POST_ENABLED=1`：总开关
- `DEEPSEEK_API_KEY`、`ALERT_WEBHOOK`

## 本地

```bash
python3 generate.py --date 2026-11-15 --out /tmp/content-bot
```
