#!/bin/bash
# 轻量健康检查：博客、评论 API、AI 助手、雷达新鲜度
set -uo pipefail

# shellcheck disable=SC1091
[ -f /etc/starry/env ] && . /etc/starry/env

fail=0
msg=""
check() {
  local name="$1" url="$2" code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" || echo 000)
  if [ "$code" = "200" ]; then
    echo "✓ $name"
  else
    echo "✗ $name ($code)"
    msg="$msg\n- $name 返回 $code"
    fail=1
  fi
}

check "博客" "https://starry-journey.github.io/"
check "评论 API" "https://starryjourney.duckdns.org:8443/api/history?room=health&limit=1"
check "AI 助手" "https://starryjourney.duckdns.org:8443/bot/health"

# 雷达最近 26 小时内是否成功跑过
if [ -f /var/lib/news-radar/run.log ]; then
  last=$(grep 'run done' /var/lib/news-radar/run.log | tail -1 | cut -d' ' -f2)
  if [ -n "$last" ]; then
    last_ts=$(date -d "$last" +%s 2>/dev/null || echo 0)
    now=$(date +%s)
    if [ $((now - last_ts)) -gt 93600 ]; then
      echo "✗ 雷达超过 26 小时未完成"
      msg="$msg\n- 雷达超过 26 小时未完成"
      fail=1
    else
      echo "✓ 雷达最近运行：$last"
    fi
  fi
fi

if [ "$fail" -ne 0 ] && [ -n "${ALERT_WEBHOOK:-}" ]; then
  text="Starry Journey 健康检查失败：$msg"
  case "${ALERT_WEBHOOK_FORMAT:-raw}" in
    feishu) payload=$(python3 -c 'import json,sys;print(json.dumps({"msg_type":"text","content":{"text":sys.argv[1]}}))' "$text") ;;
    discord) payload=$(python3 -c 'import json,sys;print(json.dumps({"content":sys.argv[1]}))' "$text") ;;
    *) payload=$(python3 -c 'import json,sys;print(json.dumps({"text":sys.argv[1]}))' "$text") ;;
  esac
  curl -s -X POST -H 'Content-Type: application/json' -d "$payload" "$ALERT_WEBHOOK" >/dev/null || true
fi

exit "$fail"
