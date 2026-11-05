# 东京新闻雷达 · 部署与运维（2026-10-30 实际部署版）

## 当前状态

| 项 | 值 |
|---|---|
| 服务器 | 207.148.111.8（Ubuntu 22.04，1C1G，Tokyo） |
| 代码 | `/opt/news-radar/`（radar/radar.py、config.yaml、deploy/） |
| 状态库 | `/var/lib/news-radar/radar.db`（SQLite 去重库） |
| 运行日志 | `/var/lib/news-radar/run.log` |
| 密钥文件 | `/etc/starry/env`（DeepSeek key，600） |
| 博客仓库副本 | `/srv/news-radar/blog`（GitHub main 的 depth=1 克隆） |
| 定时 | `news-radar.timer` 每天 08:00（Asia/Shanghai），`Persistent=true` 断电补跑 |
| 线上页面 | https://starry-journey.github.io/categories/每日简报/ |
| 登录方式 | 仅密钥：`/root/.ssh/authorized_keys`（`dsh-vpn-setup` + `dsh-vps-login-2026-10`），密码登录已关闭 |

## 数据流

```
systemd timer (每天 08:00 Asia/Shanghai)
  └─ /opt/news-radar/deploy/run.sh
       ├─ python3 radar/radar.py：23 个源 → SQLite 去重 → DeepSeek 打分+中文摘要
       ├─ 当日简报写入 /tmp/news-radar-out/source/_posts/news/YYYY-MM-DD.md
       ├─ git fetch/reset 对齐 origin/main（防止与你电脑上的提交分叉）
       ├─ 复制到 /srv/news-radar/blog/source/_posts/news/
       └─ 有变化才 commit + push → GitHub Actions 构建 → Pages 发布
```

## 常用命令

```bash
# 手动跑一次（约 1 分钟）
systemctl start news-radar.service

# 看运行日志
tail -50 /var/lib/news-radar/run.log

# 看定时器
systemctl list-timers news-radar.timer

# 改源/阈值
vim /opt/news-radar/config.yaml        # 下次运行生效

# 临时指定日期补跑（在服务器上）
cd /opt/news-radar && python3 radar/radar.py --config config.yaml --out-dir /tmp/x --date 2026-10-30

# 清空去重库（会重新抓最近 3 天）
rm /var/lib/news-radar/radar.db
```

## 推送凭据（重要）

当前为了"零人工步骤"，服务器上的推送用的是**你账号级的 `wsl2` 私钥副本**：`/root/.ssh/blog_push`
（权限 600，仅 root 可读）。它能推你 GitHub 账号下的所有仓库，不只是博客。

更安全的做法是切到**仓库专用 Deploy Key**（已在服务器生成）：
`/root/.ssh/blog_deploy.pub`
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJicsxrdlDnh+8TPZr5hEfDXKrOXYCZGU+0x+hiwuMXo blog-deploy-key
```
切换步骤：
1. 打开 https://github.com/Starry-Journey/Starry-Journey.github.io/settings/keys
2. Add deploy key → 粘贴上面公钥 → 勾选 **Allow write access** → Add key
3. 在服务器上：
   ```bash
   sed -i 's#/root/.ssh/blog_push#/root/.ssh/blog_deploy#' /opt/news-radar/deploy/run.sh
   rm -f /root/.ssh/blog_push
   sed -i '/IdentityFile \/root\/.ssh\/blog_push/d' /root/.ssh/config
   sed -i 's#IdentityFile /root/.ssh/blog_deploy#IdentityFile /root/.ssh/blog_deploy#' /root/.ssh/config 2>/dev/null || true
   systemctl start news-radar.service   # 验证仍能推送
   ```

## 已知限制

- 单源失败不影响整体，日志里会显示 `FAIL`；源地址漂移时改 `config.yaml`。
- arXiv 每次只取前 15 条（它一天几百篇），靠去重逐日滚动覆盖。
- DeepSeek 不可用时整次运行失败、不推送（宁可当天没简报，也不发半成品）。
- 当天重复运行不会把简报越跑越短（会从库里重建当日全量）。

---

## 评论区（2026-10-31 新增）

- 后端：聊天室服务 `chat-server.service`（`/opt/chat-server/chat_server`），监听 `127.0.0.1:8888`
- 数据：`/var/lib/chat-server/users.json`（账号）+ `users_chat.db`（消息，按房间存）
- 入口：`https://starryjourney.duckdns.org:8443`（nginx 反代 + Let's Encrypt 证书）
  - 443 被 sing-box 占用，所以评论区走 8443，不影响 VPN
  - DuckDNS：`starryjourney.duckdns.org` → 207.148.111.8，`/etc/duckdns/duck.sh` 每 5 分钟更新（cron）
- 前端：`source/js/comments.js` + `source/css/comments.css`，由 Hexo `inject` 注入
  - 每篇文章一个房间：房间名 = `blog-<pathname 哈希>`
  - 首次评论自动注册（昵称 + 随机密码，token 存浏览器 localStorage）
  - 每 15 秒轮询新评论

### 常用运维

```bash
# 看评论服务状态
systemctl status chat-server.service
journalctl -u chat-server.service -n 50 --no-pager

# 查看某篇文章的评论（房间哈希见浏览器 devtools 的 /api/history 请求）
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/chat-server/users_chat.db")
for row in c.execute("SELECT room,sender,content,datetime(created_at,'unixepoch','localtime') FROM messages ORDER BY id DESC LIMIT 20"):
    print(row)
PY

# 删除垃圾评论
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/chat-server/users_chat.db")
c.execute("DELETE FROM messages WHERE content LIKE '%广告%'")
c.commit()
PY

# 证书续期（certbot 会自动续；手动测试）
certbot renew --dry-run
```
