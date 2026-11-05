#!/bin/bash
# 新闻雷达执行入口：抓取 → 打分 → 写简报 → 有变化则提交并推送博客仓库
# 由 systemd timer 调用，也可手动执行：/opt/news-radar/deploy/run.sh
set -euo pipefail

APP_DIR="/opt/news-radar"
STATE_DIR="/var/lib/news-radar"
BLOG_REPO="/srv/news-radar/blog"
LOG="$STATE_DIR/run.log"
mkdir -p "$STATE_DIR"

# 环境变量（DeepSeek key 等）只放在 root 可读的 env 文件里
set -a
# shellcheck disable=SC1091
[ -f /etc/starry/env ] && . /etc/starry/env
set +a

cd "$APP_DIR"
echo "===== $(date '+%F %T') run start =====" >> "$LOG"

# 抓取/打分/写文件
# 先把仓库里已有的简报复制到 staging，便于生成"上一期/下一期"和按月索引
mkdir -p /tmp/news-radar-out/source/news
cp -a /srv/news-radar/blog/source/news/*.md /tmp/news-radar-out/source/news/ 2>/dev/null || true
python3 radar/radar.py \
  --config config.yaml \
  --out-dir /tmp/news-radar-out \
  --db "$STATE_DIR/radar.db" >> "$LOG" 2>&1 || { echo "radar failed, see $LOG" >> "$LOG"; exit 1; }

# 先与远端对齐，避免你在电脑上推过博客后这里出现分叉
cd "$BLOG_REPO"
git fetch -q origin main >> "$LOG" 2>&1
git reset --hard -q origin/main >> "$LOG" 2>&1

# 把新简报同步进博客仓库（只写脚本自己生成的目录，绝不动手写文章）
mkdir -p source/news
cp -a /tmp/news-radar-out/source/news/. source/news/

git config user.name "news-radar"
git config user.email "news-radar@users.noreply.github.com"
if git status --porcelain -- source/news | grep -q .; then
  git add source/news
  git commit -q -m "chore(news): update daily digest $(date +%F)" >> "$LOG" 2>&1
  if GIT_SSH_COMMAND="ssh -i /root/.ssh/blog_push -o IdentitiesOnly=yes" git push -q origin main >> "$LOG" 2>&1; then
    echo "pushed $(date +%F)" >> "$LOG"
  else
    echo "push FAILED $(date +%F)" >> "$LOG" >&2
    exit 1
  fi
else
  echo "no new digest, skip push" >> "$LOG"
fi
echo "===== $(date '+%F %T') run done =====" >> "$LOG"
