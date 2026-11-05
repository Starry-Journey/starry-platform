#!/usr/bin/env python3
"""博客 AI 助手后端：接收前端对话，调用 DeepSeek，返回回复。

- 无第三方 web 框架，仅标准库 + requests
- 每个 IP 限流（默认 20 次/分钟）
- 单次最多带 12 条历史，回复最多 500 tokens
"""
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

PORT = int(os.environ.get("CHATBOT_PORT", "8890"))
API_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
PROMPT_FILE = os.environ.get("CHATBOT_PROMPT", "/opt/chatbot/prompt.txt")
ALLOWED_ORIGINS = {
    "https://starry-journey.github.io",
    "http://localhost:4000",
    "http://127.0.0.1:4000",
}
MAX_HISTORY = 12
MAX_CHARS = 2000
RATE_LIMIT = 20          # 次
RATE_WINDOW = 60         # 秒
DAILY_LIMIT = int(os.environ.get("CHATBOT_DAILY_LIMIT", "300"))
USAGE_FILE = "/opt/chatbot/usage.json"

_lock = threading.Lock()
_buckets = {}            # ip -> [timestamps]


def load_prompt():
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "你是博客的 AI 小助手，回答简短、友好、用中文。"


def rate_ok(ip):
    now = time.time()
    with _lock:
        q = _buckets.setdefault(ip, [])
        q[:] = [t for t in q if now - t < RATE_WINDOW]
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        return True


def daily_ok():
    # 全站每日请求上限，防止被刷
    today = time.strftime("%Y-%m-%d")
    with _lock:
        data = {"date": today, "count": 0}
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        if data.get("date") != today:
            data = {"date": today, "count": 0}
        if data["count"] >= DAILY_LIMIT:
            return False
        data["count"] += 1
        try:
            with open(USAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass
        return True


def clean_messages(raw):
    out = []
    if not isinstance(raw, list):
        return out
    for m in raw[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            content = content.strip()[:MAX_CHARS]
            if content:
                out.append({"role": role, "content": content})
    # 必须由用户发言结尾
    while out and out[-1]["role"] != "user":
        out.pop()
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "StarryChat/1.0"

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "https://starry-journey.github.io")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/api/chat"):
            self._json(404, {"error": "not found"})
            return
        ip = self.headers.get("X-Real-IP") or self.client_address[0]
        if not rate_ok(ip):
            self._json(429, {"error": "慢一点呀，喘口气再聊~"})
            return
        if not daily_ok():
            self._json(429, {"error": "今天聊得太多啦，明天再来找大肥鱼玩吧~"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "bad request"})
            return

        msgs = clean_messages(data.get("messages"))
        if not msgs:
            self._json(400, {"error": "说点什么吧"})
            return

        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": load_prompt()}] + msgs,
            "temperature": 0.8,
            "max_tokens": 500,
        }
        try:
            resp = requests.post(
                API_BASE + "/chat/completions",
                json=payload,
                timeout=90,
                headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # 不把内部错误细节暴露给前端
            print("upstream error:", repr(exc), flush=True)
            self._json(502, {"error": "大肥鱼暂时连不上脑子啦，稍后再试~"})
            return
        # 去掉模型偶尔带出的 markdown 标题
        reply = re.sub(r"^#+\s*", "", reply)
        self._json(200, {"reply": reply})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main():
    if not API_KEY:
        raise SystemExit("DEEPSEEK_API_KEY 未设置")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"chatbot listening on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
