#!/bin/bash
# 每日随笔：生成 → 推 daily-日期 分支 → Actions 开草稿 PR
set -euo pipefail

APP_DIR="/opt/content-bot"
BLOG_REPO="/srv/content-bot/blog"
LOG="/var/log/content-bot.log"
DATE=$(date +%F)
BRANCH="daily-$DATE"

# shellcheck disable=SC1091
[ -f /etc/starry/env ] && . /etc/starry/env
[ "${DAILY_POST_ENABLED:-0}" = "1" ] || { echo "DAILY_POST_ENABLED != 1, skip" >>"$LOG"; exit 0; }

if [ ! -d "$BLOG_REPO/.git" ]; then
  mkdir -p "$(dirname "$BLOG_REPO")"
  GIT_SSH_COMMAND="ssh -i /root/.ssh/blog_push -o IdentitiesOnly=yes" \
    git clone -q git@github.com:Starry-Journey/Starry-Journey.github.io.git "$BLOG_REPO"
fi

cd "$BLOG_REPO"
git fetch -q origin main
git reset --hard -q origin/main

if [ -f "source/_posts/$DATE-daily.md" ]; then
  echo "$DATE already exists, skip" >>"$LOG"
  exit 0
fi

git checkout -q -B "$BRANCH"
"$APP_DIR/venv/bin/python" "$APP_DIR/generate.py" --date "$DATE" --out "$BLOG_REPO" >>"$LOG" 2>&1

git add source/_posts source/images/covers
git commit -q -m "feat: 每日随笔 $DATE" >>"$LOG" 2>&1
GIT_SSH_COMMAND="ssh -i /root/.ssh/blog_push -o IdentitiesOnly=yes" \
  git push -f -q origin "$BRANCH" >>"$LOG" 2>&1

if [ -n "${ALERT_WEBHOOK:-}" ]; then
  URL="https://github.com/Starry-Journey/Starry-Journey.github.io/compare/main...$BRANCH?expand=1"
  TEXT="✍️ 今日随笔草稿已生成：$DATE
打开 PR 审核后合并：
$URL"
  PAYLOAD=$(python3 -c 'import json,sys;print(json.dumps({"msg_type":"text","content":{"text":sys.argv[1]}}))' "$TEXT")
  curl -s --max-time 15 -X POST -H 'Content-Type: application/json' -d "$PAYLOAD" "$ALERT_WEBHOOK" >/dev/null || true
fi
