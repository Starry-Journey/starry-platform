# VPS 基础设施（Ansible）

把服务器基线（软件包、时区、防火墙、目录）变成可重复执行的代码。

```bash
cd infra/ansible
cp inventory.example inventory.ini   # 填自己的主机
ansible-playbook site.yml --check    # 只检查，不改动
ansible-playbook site.yml            # 实际执行
```

## 边界

- 这里只负责**主机基线**；应用代码与配置由备份仓库恢复（见 `docs/LAYER1.md`）
- 密钥不在仓库里，首次部署后从加密备份恢复 `/etc/starry/env`
- `--check` 模式对 `ufw`/`service` 模块可能显示 changed，属正常
