#!/bin/bash
# 备份恢复演练：拉取备份仓库 → 解密最新 secrets → 校验关键文件
set -euo pipefail

REPO_DIR="${1:-/tmp/starry-restore-drill}"
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -i /root/.ssh/blog_push -o IdentitiesOnly=yes}"
: "${BACKUP_PASSPHRASE:?请设置 BACKUP_PASSPHRASE 环境变量}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull -q --ff-only
else
  git clone -q --depth 1 git@github.com:Starry-Journey/starry-backup.git "$REPO_DIR"
fi

LATEST=$(find "$REPO_DIR/secrets" -name "*.enc" -printf "%T@ %p\n" | sort -rn | head -1 | cut -d" " -f2-)
echo "最新备份：$(basename "$LATEST")"

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass "pass:$BACKUP_PASSPHRASE" -in "$LATEST" | tar -xz -C "$WORK"

fail=0
for f in starry.env starry-db.sql.gz sing-box-config.json; do
  if [ -s "$WORK/$f" ]; then echo "✓ secrets/$f"; else echo "✗ secrets/$f"; fail=1; fi
done

for f in scripts/news-radar/radar/radar.py scripts/chatbot/service.py \
         scripts/systemd/chatbot.service scripts/nginx/chat-comments; do
  if [ -s "$REPO_DIR/$f" ]; then echo "✓ $f"; else echo "✗ $f"; fail=1; fi
done

if [ "$fail" -ne 0 ]; then
  echo "恢复演练失败"
  exit 1
fi
echo "恢复演练通过：备份可解密、关键文件齐全"
