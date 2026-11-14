#!/bin/bash
# 每日飞书报告：服务器资源、服务状态、简报、可选 Vultr 余额
set -uo pipefail

# shellcheck disable=SC1091
[ -f /etc/starry/env ] && . /etc/starry/env

WEBHOOK="${ALERT_WEBHOOK:-}"
if [ -z "$WEBHOOK" ]; then
  echo "ALERT_WEBHOOK 未配置" >&2
  exit 1
fi

DATE=$(date '+%Y-%m-%d %H:%M')
MEM=$(free -m | awk 'NR==2{printf "%s/%s MB (%.0f%%)", $3, $2, $3*100/$2}')
DISK=$(df -h / | awk 'NR==2{printf "%s/%s (%s)", $3, $2, $5}')
LOAD=$(cut -d' ' -f1-3 /proc/loadavg)
UPTIME=$(uptime -p | sed 's/^up //')
RADAR=$(grep 'run done' /var/lib/news-radar/run.log 2>/dev/null | tail -1 | awk '{print $2" "$3}')
[ -z "$RADAR" ] && RADAR="无记录"

SERVICES=""
for s in starry-api nginx postgresql; do
  if systemctl is-active --quiet "$s"; then
    SERVICES="$SERVICES $s✅"
  else
    SERVICES="$SERVICES $s❌"
  fi
done

VULTR="Vultr 余额：未配置 VULTR_API_KEY"
if [ -n "${VULTR_API_KEY:-}" ]; then
  ACC=$(curl -s --max-time 15 -H "Authorization: Bearer $VULTR_API_KEY" https://api.vultr.com/v2/account)
  PARSED=$(printf '%s' "$ACC" | python3 -c '
import json,sys
try:
    a=json.load(sys.stdin)["account"]
    print(f"Vultr 余额：{a.get(\"balance\",\"?\")} USD（待扣 {a.get(\"pending_charges\",\"?\")} USD）")
except Exception:
    print("Vultr 余额：查询失败")
' 2>/dev/null) || PARSED="Vultr 余额：查询失败"
  VULTR="$PARSED"
fi

MSG="🌌 Starry Journey 每日报告
$DATE

🖥 内存 $MEM
💾 磁盘 $DISK
📈 负载 $LOAD · 已运行 $UPTIME
🔧 服务$SERVICES
📰 简报最近运行：$RADAR
💰 $VULTR"

PAYLOAD=$(python3 -c 'import json,sys;print(json.dumps({"msg_type":"text","content":{"text":sys.argv[1]}}))' "$MSG")
RESP=$(curl -s --max-time 15 -X POST -H 'Content-Type: application/json' -d "$PAYLOAD" "$WEBHOOK")
echo "feishu: $RESP"
