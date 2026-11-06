#!/bin/bash
# Starry Journey 运维备份
#  - scripts/  可读的代码与配置（新闻雷达、聊天室、AI 助手、nginx、systemd、VPN 说明）
#  - secrets/  加密包（API key、DuckDNS token、sing-box 配置）
# 推送到私有仓库 github.com/Starry-Journey/starry-backup
set -euo pipefail

REPO_URL="git@github.com:Starry-Journey/starry-backup.git"
SSH_KEY="/root/.ssh/blog_push"
GIT_SSH="ssh -i $SSH_KEY -o IdentitiesOnly=yes"
WORK="/tmp/starry-backup-work"
STAGE="$WORK/stage"
PASS_FILE="/etc/backup/passphrase"
KEEP_SECRETS=7
DATE=$(date +%F)

rm -rf "$WORK"
mkdir -p "$STAGE"/{scripts/{news-radar,chatbot,chat-server,systemd,nginx,duckdns,vpn},secrets}

# ---------- 可读脚本与配置 ----------
cp -a /opt/news-radar/radar /opt/news-radar/deploy /opt/news-radar/docs \
      /opt/news-radar/config.yaml "$STAGE/scripts/news-radar/" 2>/dev/null || true
cp -a /opt/chatbot/service.py /opt/chatbot/prompt.txt "$STAGE/scripts/chatbot/" 2>/dev/null || true
mkdir -p "$STAGE/scripts/chat-server"
cp -a /opt/chat-server/Makefile /opt/chat-server/src /opt/chat-server/include \
      /opt/chat-server/lib /opt/chat-server/web "$STAGE/scripts/chat-server/" 2>/dev/null || true
cp -a /etc/systemd/system/chatbot.service /etc/systemd/system/chat-server.service \
      /etc/systemd/system/news-radar.service /etc/systemd/system/news-radar.timer \
      /etc/systemd/system/starry-backup.service /etc/systemd/system/starry-backup.timer \
      "$STAGE/scripts/systemd/" 2>/dev/null || true
cp -a /lib/systemd/system/sing-box.service "$STAGE/scripts/systemd/" 2>/dev/null || true
cp -a /etc/nginx/sites-available/chat-comments "$STAGE/scripts/nginx/" 2>/dev/null || true
grep -n 'duckdns' /etc/crontab > "$STAGE/scripts/duckdns/crontab.txt" 2>/dev/null || true
cp -a /etc/duckdns/duck.sh "$STAGE/scripts/duckdns/duck.sh" 2>/dev/null || true

cat > "$STAGE/scripts/vpn/README.md" <<'EOF'
# VPN（sing-box）

- 版本：1.14.4（deb 包安装，`apt install sing-box`）
- 服务：`systemctl status sing-box`，配置目录 `/etc/sing-box/`
- 配置 `config.json` 含私钥，放在本仓库 `secrets/` 加密包内
- 重装：安装同版本 sing-box 包 → 恢复 config.json → `systemctl enable --now sing-box`

监听 443（VLESS Reality），博客评论区使用 8443，两者不冲突。
EOF

# 清理无用文件
find "$STAGE/scripts" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/scripts" -name '*.pyc' -delete 2>/dev/null || true

# ---------- 加密：密钥与敏感配置 ----------
SECRETS="$WORK/secrets"
mkdir -p "$SECRETS"
cp -a /etc/starry/env "$SECRETS/starry.env" 2>/dev/null || true
cp -a /etc/sing-box/config.json "$SECRETS/sing-box-config.json" 2>/dev/null || true
# Postgres 逻辑备份
if command -v pg_dump >/dev/null 2>&1 && [ -f /root/.starry_pg ]; then
  PGPASS=$(sed -n 's/^PGPASS=//p' /root/.starry_pg)
  PGPASSWORD="$PGPASS" pg_dump -h 127.0.0.1 -U starry starry 2>/dev/null | gzip > "$SECRETS/starry-db.sql.gz" || true
fi
tar czf "$WORK/secrets-$DATE.tar.gz" -C "$SECRETS" .
openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
  -pass "file:$PASS_FILE" -in "$WORK/secrets-$DATE.tar.gz" \
  -out "$STAGE/secrets/secrets-$DATE.tar.gz.enc"

# ---------- 说明文件 ----------
cat > "$STAGE/README.md" <<EOF
# Starry Journey 运维备份

自动生成于 $DATE。用于 VPS 误删/重装后的快速恢复。

## 目录

- \`scripts/news-radar/\`  新闻雷达代码、配置、systemd 单元
- \`scripts/chatbot/\`    AI 助手后端与人设
- \`scripts/chat-server/\` 聊天室/评论区源码（C++）
- \`scripts/systemd/\`    服务单元文件
- \`scripts/nginx/\`      评论区反向代理配置
- \`scripts/vpn/\`        sing-box VPN 说明与版本
- \`secrets/secrets-*.tar.gz.enc\`  加密包：API key、DuckDNS token、sing-box 配置

加密包用 AES-256 加密，口令不在本仓库（在管理员密码管理器里）。

## 恢复

1. 新建 Ubuntu 22.04 实例，安装依赖：
   \`apt install -y python3-pip git nginx certbot python3-certbot-nginx g++ nlohmann-json3-dev sqlite3\`
2. 克隆本仓库，按 \`scripts/\` 恢复代码与配置到对应路径。
3. 解密 \`secrets/\` 后放回 \`/etc/chatbot/env\`、\`/etc/news-radar/env\`、\`/etc/duckdns/duck.sh\`、\`/etc/sing-box/config.json\`。
4. 更新 DuckDNS 指向新 IP，申请证书，启动服务。
5. 详细步骤见本地 \`starry-journey/docs/RESTORE.md\`。
EOF

# ---------- 同步到私有仓库 ----------
REPO="$WORK/repo"
if [ ! -d "$REPO/.git" ]; then
  if ! GIT_SSH_COMMAND="$GIT_SSH" git clone -q "$REPO_URL" "$REPO" 2>/dev/null; then
    mkdir -p "$REPO" && git -C "$REPO" init -q
  fi
  git -C "$REPO" remote set-url origin "$REPO_URL" 2>/dev/null || true
fi

# 仓库为空时创建 main 分支
if ! git -C "$REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
  git -C "$REPO" checkout -q -b main
fi

# 用最新内容覆盖（保留 .git）
find "$REPO" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$STAGE/." "$REPO/"

# 加密包只保留最近 N 份
find "$REPO/secrets" -name "secrets-*.tar.gz.enc" -printf "%T@ %p\n" 2>/dev/null | sort -rn | tail -n +$((KEEP_SECRETS + 1)) | cut -d" " -f2- | xargs -r rm -f

cd "$REPO"
git config user.name "backup-bot"
git config user.email "backup@local"
git add -A
if git diff --cached --quiet; then
  echo "[$(date '+%F %T')] no changes"
else
  git commit -qm "backup: $DATE"
  GIT_SSH_COMMAND="$GIT_SSH" git push -q -u origin HEAD:main
  echo "[$(date '+%F %T')] pushed backup $DATE"
fi

rm -rf "$WORK"
