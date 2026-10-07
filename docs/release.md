# 发布与安装

## 三件产物

| 产物 | 内容 | 谁怎么用它 |
|---|---|---|
| `chrome_agent-<v>-py3-none-any.whl` | 只有 `chrome_agent/` 包 | `install.sh` 装进 venv，提供 `chrome-agent` CLI、daemon、Native Messaging host |
| `chrome-agent-extension-<v>.zip` | `extension/` 的全部内容 | 用户在 `chrome://extensions` 里加载（开发者模式 → 加载已解压的扩展程序，选解压后的目录） |
| `chrome-agent-skill-<v>.tar.gz` | `skill/chrome-agent/`（含 `sites/`） | 智能体读；`install.sh` 复制或软链到 `~/.claude/skills/`、`~/.codex/skills/` |
| `chrome-agent-<v>-bundle.tar.gz` | 上面三件 + `install.sh` + README + LICENSE | 不想留仓库的用户：解压 → `./install.sh` → 删掉解压目录 |

`./release.sh` 一次生成全部产物与 `SHA256SUMS`。

## 两种安装模式

`install.sh` 按脚本旁边有什么来区分：

- **checkout**（目录里有 `pyproject.toml`）：现构建 wheel 装进 venv，并把 skill **软链**回仓库——改 skill 或站点脚本立刻生效，不用重装。开发时用这种。
- **bundle**（目录里有 `chrome_agent-*.whl`）：直接装这个 wheel，并把 skill **复制**到 agent 技能目录。装完仓库可以删。

两种模式都做这些事：

1. venv 建在 `~/.chrome-agent/venv`（可用 `CHROME_AGENT_VENV` 改）。
2. 非 editable 安装 wheel，所以运行时不再指向源码目录（旧版是 `pip install -e`，导致仓库成为运行时依赖）。
3. 从 `extension/manifest.json` 的 `key` 算出扩展 ID，写进 Native Messaging host 清单 `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.browseruse.chrome_agent.json`。
4. 把 launcher 写到 `~/.chrome-agent/launcher.sh`（**不再写进仓库**），内容是 `exec <venv>/bin/python -m chrome_agent.native_host.native_host`。
5. 安装 skill 到 `~/.claude/skills/chrome-agent` 与 `~/.codex/skills/chrome-agent`（可用 `--skill-dirs` 改）。
6. 记录 `~/.chrome-agent/install.json`（版本、扩展 ID、skillDir 等），`chrome-agent playbook` 靠它找到站点目录。
7. 把 CLI 软链到 `~/.local/bin/chrome-agent`。

`./install.sh --uninstall [--purge]` 反向清理（`--purge` 连 venv 一起删）；扩展本身在 `chrome://extensions` 里移除。

## 扩展 ID 为什么是固定的

`extension/manifest.json` 里的 `key` 是扩展的公钥。Chrome 用它派生 ID：公钥的 SHA256、取前 16 字节的十六进制、再把每个十六进制位映射到 `a`-`p`（Chromium `components/crx_file/id_util.cc`：`kIdSize = 16`「First 16 bytes of SHA256 hashed public key」，以及 `ConvertHexadecimalToIDAlphabet` 里「用 'a'-'p' 而不是 '0'-'f'，以免出现纯数字 host 被当成 IP」的注释）。官方文档 [Manifest - key](https://developer.chrome.com/docs/extensions/reference/manifest/key) 说明该字段就是用来「在开发加载时保持扩展 ID 不变」的。

于是安装时不必再让用户去 `chrome://extensions` 抄一串 32 位 ID 传给脚本：`install.sh` 自己按同一算法算出来（`chrome_agent/utils/extension_id.py`，与 `install.sh` 共用同一份实现）。

代价是一次性的：加 `key` 后扩展 ID 变化，需要在 `chrome://extensions` 重新加载扩展，脚本会打印应显示的 ID 供核对。已经授予的可选站点权限会重置（`host_permissions` 里的站点不受影响）。

如果某台机器故意不加 `key` 加载（例如临时改代码调试），用 `./install.sh --extension-id <chrome://extensions 显示的 ID>` 覆盖。

## 私钥

签发 `.crx` 需要私钥，本仓库不含私钥。本机生成并保存在：

```text
~/.chrome-agent/extension-key.pem      # 0600，仅本机
```

**它必须备份。** 丢了它就无法再用同一 ID 签发 `.crx`（unpacked 加载不受影响，因为 ID 只由 manifest 里的公钥决定）。`.gitignore` 里的 `*.pem` 是防止它被误提交的第二道闸。
