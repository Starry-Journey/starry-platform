# Layer 1 运行手册（IaC / 监控 / 恢复演练）

## 1. 分支保护（需要仓库管理员，在网页点 2 分钟）

GitHub → 仓库 **Settings → Branches → Add branch protection rule**：

- Branch name pattern：`main`
- 勾选 **Require a pull request before merging**
- 勾选 **Require status checks to pass before merging**
  - 搜索并勾选：`CI / build`、`CI / pr-title`
- 勾选 **Require branches to be up to date before merging**
- 勾选 **Do not allow bypassing the above settings**
- 保存

之后直接 push main 会被拒绝，必须走 PR 且 CI 通过。

> 没有管理员 token 时无法用 API 自动完成；网页操作即可。

## 2. 创建 starry-platform 仓库

在 GitHub 新建**私有**空仓库 `starry-platform`（不要勾选 README），然后：

```bash
cd ~/starry-journey/platform
git remote add origin git@github.com:Starry-Journey/starry-platform.git
git push -u origin main
```

推送后 `Platform CI` 会自动跑：pytest（news-radar / chatbot）+ ruff + shellcheck。

## 3. 性能预算

博客仓库 CI 现在包含：

- `npm run test:budget`：太阳系脚本 ≤120KB、three.js vendor ≤700KB、贴图目录 ≤1MB
- `npm run test:lighthouse`：首页与 `/solar/` 的性能、LCP、CLS、总字节数
- Playwright 里的 FPS 冒烟：3D 初始化 <12s、帧率 >15（本机实测 2.3s / 22.7fps）

调阈值改 `lighthouserc.json` 与 `scripts/check-bundle-budget.mjs`。

## 4. IaC（Ansible）

```bash
cd platform/infra/ansible
cp inventory.example inventory.ini
ansible-playbook site.yml --check   # 先看会改什么
ansible-playbook site.yml
```

只负责主机基线（包、时区、防火墙、目录）；应用代码与密钥从备份恢复。

## 5. 监控

已部署：

- `starry-healthcheck.timer` 每 10 分钟检查：博客、评论 API、AI 助手、雷达是否 26 小时内跑过
- 失败时若 `/etc/starry/env` 里配置了 `ALERT_WEBHOOK`，会 POST 一条 JSON 消息

```bash
systemctl list-timers starry-healthcheck.timer
journalctl -u starry-healthcheck.service -n 20 --no-pager
```

**接告警**：把飞书/钉钉/Telegram 机器人的 webhook 填到 `/etc/starry/env` 的 `ALERT_WEBHOOK=`，然后 `systemctl restart starry-healthcheck.timer`（或等下一轮）。

## 6. 恢复演练（已执行通过）

```bash
ssh vps-tokyo 'BACKUP_PASSPHRASE=$(cat /etc/backup/passphrase) /usr/local/bin/starry-restore-drill.sh'
```

会拉取私有备份仓库、解密最新 secrets、校验关键文件。当前结果：全部通过。

## 7. 下一步

- 选一个告警渠道（飞书机器人最省事）填入 `ALERT_WEBHOOK`
- 给 `starry-platform` 也开分支保护
- Layer 2：FastAPI 统一后端（chat 流式、评论、占星）
