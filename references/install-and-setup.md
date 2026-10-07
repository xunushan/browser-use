# 安装与配置

只有在 `chrome-agent` 命令不存在、或扩展连不上时才读本文件。装好之后不用再管它。

## 这套东西由什么组成

这个 skill 目录**就是**全部：说明书（`SKILL.md`）、运行时（`chrome_agent/`）、
Chrome 扩展（`extension/`）、配置脚本（`setup.sh`）。没有别的包要下载。

装好之后各部分落在哪：

| 东西 | 位置 |
|---|---|
| 运行时 | 本目录，`uv` 装进 `~/.chrome-agent/venv`（可用 `CHROME_AGENT_VENV` 改） |
| Native Messaging host 清单 | `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.browseruse.chrome_agent.json` |
| Chrome 执行的入口 | `~/.chrome-agent/launcher.sh`（由 `setup.sh` 生成，绝对路径写死） |
| CLI | `~/.local/bin/chrome-agent` → venv 里的同名命令 |
| 安装记录 | `~/.chrome-agent/install.json`（版本、扩展 ID、skill 位置） |

前四处的路径都可以用环境变量覆盖（`CHROME_AGENT_HOME`、`CHROME_AGENT_VENV`、
`CHROME_AGENT_BIN_DIR`、`CHROME_AGENT_HOST_DIR`），`setup.sh --help` 里有。

## 前置

- macOS（暂只支持）+ 已安装的 Google Chrome；
- `uv`。没有就装上，它同时让 pip 和 venv 不必出现在用户面前：

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## 步骤

### 1. 把 skill 放到智能体读技能的地方

本目录就是 skill，放到技能目录即完成"安装 skill"这一步——`SKILL.md` 在这里，
`chrome_agent/` 和 `extension/` 也在同一层，脚本不用去别处找东西。

```bash
git clone https://github.com/xunushan/browser-use.git ~/.claude/skills/chrome-agent
```

用软链也可以（开发时更顺手，改动立即生效）：

```bash
ln -s <本仓库路径> ~/.claude/skills/chrome-agent
```

### 2. 运行 setup.sh

```bash
<skill 目录>/setup.sh
```

它做四件事：用 `uv` 建 venv 并从本目录可编辑安装运行时；按 `extension/manifest.json`
里的 `key` 算出扩展 ID；写 Native Messaging host 清单与 launcher；把本目录软链到
`~/.claude/skills/chrome-agent` 和 `~/.codex/skills/chrome-agent`（`--skill-dirs` 可改）。

### 3. 加载扩展 —— 唯一需要用户动手的一步

Chrome 不提供静默安装路径：扩展必须由用户在 `chrome://extensions` 上亲自加载。
`--load-extension` 这个命令行开关已在 Chrome 137 从正式版构建中移除，官方给出的两个
替代（CDP `Extensions.loadUnpacked`、WebDriver BiDi `webExtension.install`）都要求另起
一个受调试驱动的 Chrome 实例，拿不到用户这个已登录的 Chrome，对本项目没有用。

来源：Chrome for Developers《What's happening in Chrome Extensions, June 2025》
（2025-06-06，`--load-extension` 被滥用为由宣布移除）；
chromium-extensions 邮件组 PSA "Removing `--load-extension` in Chrome 137"（2025-03-18）；
Cypress issue #31690（2025-05-12，列出上述两个替代方案）。

用户在场时，可以替他把页面和文件夹打开：

```bash
open -a "Google Chrome" "chrome://extensions"
open "<skill 目录>/extension"
```

然后告诉他：打开右上角**开发者模式** → **加载已解压的扩展程序** → 选上面打开的
`extension` 文件夹 → 卡片上显示的 ID 必须与 `setup.sh` 打印的一致（ID 由清单里的
`key` 固定，换机器也不变）。不一致说明选错了文件夹。

### 4. 验证

```bash
chrome-agent ensure --launch-if-missing --wait-for-extension --timeout 30 --json
```

`"daemon": true` 且 `"extension": true` 才算通。之后按 `SKILL.md` 第 1 节继续。

## 装不上时先看这几条

| 现象 | 原因与处理 |
|---|---|
| `ensure` 报 `"extension": false` 但扩展已加载 | 卡片上的 ID 与 host 清单里的不一致——多半加载的不是本目录的 `extension/`，或清单被改过。删掉重新加载，核对 ID |
| Chrome 更新/重启后扩展显示"已停用"或报错 | 在 `chrome://extensions` 上重新加载扩展即可；host 清单不用动 |
| `command not found: chrome-agent` | `~/.local/bin` 不在 PATH，或 `setup.sh` 没跑完 |
| `command not found: uv` | 先按上面的命令装 uv，再重跑 `setup.sh` |
| 想换扩展 ID | 正常情况下不要：清单里的 `key` 已经把 ID 固定了。确要覆盖时用 `setup.sh --extension-id <id>` |

## 卸载

```bash
<skill 目录>/setup.sh --uninstall          # 加 --purge 连 venv 一起删
```

扩展本身在 `chrome://extensions` 上移除。`--uninstall` 只删本脚本创建的软链，
不会删真正的 skill 目录。
