# 安装与配置

只有在 `chrome-agent` 命令不存在、或扩展连不上时才读本文件。装好之后不用再管它——
**重装或更新 skill 不需要重新装扩展**，见下面第 3 步。

## 这套东西由什么组成

`chrome-agent` 是一个**工具**，装在自己的安装目录 `~/chrome-agent/` 下。技能目录里只有
**说明书**——`SKILL.md` 和 `references/`。两者是分开的：读说明书不该依赖找到源代码。

一次安装把这几样东西放到它们该在的地方：

| 东西 | 位置 |
|---|---|
| 运行时 | `~/chrome-agent/venv`（`uv` 装进去，可用 `CHROME_AGENT_VENV` 改） |
| Chrome 加载的扩展 | `~/chrome-agent/extension`，由 `setup.sh` 从仓库的 `extension/` 同步 |
| Native Messaging host 清单 | macOS：`~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.browseruse.chrome_agent.json`；Linux：`~/.config/google-chrome/NativeMessagingHosts/com.browseruse.chrome_agent.json` |
| Chrome 执行的入口 | `~/chrome-agent/launcher.sh`（由 `setup.sh` 生成，绝对路径写死） |
| CLI | `~/.local/bin/chrome-agent` → venv 里的同名命令 |
| **说明书** | `~/.claude/skills/chrome-agent/`，其中只有 `SKILL.md` 与 `references/` |
| 安装记录 | `~/chrome-agent/install.json` |

**运行时是正式安装，不是 editable。** 装完仓库可以删掉，`chrome-agent` 照常工作。代价是
改了仓库里的代码要重跑 `setup.sh` 才生效——说明书也是同一次跑同步过去的，两者不会脱节。

技能目录是**拷贝**而不是软链，道理一样：那里是给智能体读的说明书，不该同时又是一个项目
的副本。代价相同：改了 `SKILL.md` 或 `references/` 要重跑 `setup.sh`，智能体才读得到新的。

扩展单独放一份、而不是就地加载仓库里的 `extension/`，是因为 Chrome 记住的是它加载时那个
**目录路径**：仓库一旦被移动或删掉，就地加载的扩展就会失效。放在 `~/chrome-agent/extension`
之后，更新动不到它。

安装目录叫 `~/chrome-agent` 而不是 `~/.chrome-agent`，是为了上面第 3 步那一次人工选择：
**macOS 的文件选择框不列出点开头的目录**，"加载已解压的扩展程序"的选文件夹面板里根本
看不到隐藏目录，也就选不中。放在家目录下的可见位置，这个路径点两下就能选到。

早于这次改动的安装不会被自动搬走（旧目录里可能还放着你自己的东西，不是本脚本的财产），
`setup.sh` 只会在结尾提示它还在。要收尾就：在 `chrome://extensions` 上删掉从
`~/.chrome-agent/extension` 加载的那张卡，改从 `~/chrome-agent/extension` 加载，然后
看过内容再决定旧目录怎么处理——**旧那份扩展副本不会再被更新**。

路径都可以用环境变量覆盖（`CHROME_AGENT_HOME`、`CHROME_AGENT_VENV`、
`CHROME_AGENT_BIN_DIR`、`CHROME_AGENT_HOST_DIR`），`setup.sh --help` 里有。
浏览器是 Chromium 而非 Chrome 时，把 `CHROME_AGENT_HOST_DIR` 指到
`~/.config/chromium/NativeMessagingHosts`（macOS 上是
`~/Library/Application Support/Chromium/NativeMessagingHosts`）。清单目录的官方依据：
Chrome for Developers《Native messaging》的用户级目录表与 Chromium 的
`install_host.sh` 示例脚本。

## 前置

- macOS 或 Linux（Windows 未验证：host 靠注册表注册、daemon 用的是 Unix domain
  socket，两条都没在真机上跑过）+ 已安装的 Google Chrome；
- `uv`。没有就装上，它同时让 pip 和 venv 不必出现在用户面前：

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## 步骤

### 1. 拿到仓库

`setup.sh` 从仓库里读源码、扩展和说明书，所以先要有仓库。**放哪都行**——装完它就不重要了。

要改这个工具，`git clone`：

```bash
git clone https://github.com/xunushan/chrome-agent.git ~/projects/chrome_agent
```

只想用，下载归档（已剔除开发用的 `tests/`、`docs/`，见 `.gitattributes` 的 `export-ignore`）：

```bash
mkdir -p /tmp/chrome-agent && cd /tmp/chrome-agent
curl -fsSL https://github.com/xunushan/chrome-agent/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1
```

**不要把仓库解到 `~/.claude/skills/chrome-agent`。** 那里是技能目录，`setup.sh` 要往里写
说明书；仓库若放在那儿，它会发现自己要覆盖的正是自己的源码目录，于是**停手不动**。这是
防误删的守卫（否则会把 `chrome_agent/`、`extension/`、`setup.sh` 删掉给四个文件腾地方），
不是故障。

### 2. 运行 setup.sh

```bash
<仓库目录>/setup.sh
```

它做六件事：用 `uv` 建 venv 并**正式安装**运行时；按 `extension/manifest.json` 里的 `key`
算出扩展 ID（换机器也不变）；把 `extension/` 同步到 `~/chrome-agent/extension`；写 Native
Messaging host 清单与 launcher；把 `chrome-agent` 链到 `~/.local/bin`；把 `SKILL.md` 与
`references/` 拷进 `~/.claude/skills/chrome-agent`。

最后一件会把技能目录**换成一个真实目录**。早先版本在这里放的是指向仓库的软链，这次运行
会把它换成只装说明书的目录——**仓库本身不受影响，代码一个字节都不会删**。

它结尾会自己判断扩展那一摊该不该动**再**说话，所以打印出来的就是当前该做的事。

### 3. 加载扩展 —— 只有第一次需要，而且只有一次

**先看 `setup.sh` 结尾说了什么。** 它已经问过 daemon：扩展连上没有。

- "已就绪" / "已经在这份拷贝上" → 扩展不用管，直接跳到第 4 步；
- "已重载" → 更新后的文件已被扩展自己读进去，也不用管；
- "Chrome 没在运行" → 无法确认；但扩展加载过就一直有效，同样不用做任何事；
- 只有打印 "One step is left" 时，才说明扩展从没在这台机器上加载过。

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
# macOS
open -a "Google Chrome" "chrome://extensions"
open ~/chrome-agent/extension
# Linux
google-chrome "chrome://extensions"
xdg-open ~/chrome-agent/extension
```

然后告诉他：打开右上角**开发者模式** → **加载已解压的扩展程序** → 选
`~/chrome-agent/extension` → 卡片上显示的 ID 必须与 `setup.sh` 打印的一致。

两条硬约束：

- **开发者模式要一直开着。** Chrome 133 起，未打包扩展只在开发者模式开启时启用，
  关掉它等于禁用扩展。来源：Chrome for Developers《Extension news, January 2025》。
- **重装 skill 不等于重装扩展。** 扩展不在 skill 目录里，Chrome 记的是
  `~/chrome-agent/extension`；重跑 `setup.sh` 时扩展会自己重载到新文件。
  扩展重载后，**已经打开的页面要刷新一下**，页面里已注入的 content script 还是旧代码。

### 4. 验证

```bash
chrome-agent extension status --json
chrome-agent ensure --launch-if-missing --wait-for-extension --timeout 30 --json
```

第一条回答"装没装、跑的是不是磁盘上这份"：`"connected": true` 即通。第二条把 daemon
和 Chrome 都拉起来再确认一次，`"daemon": true` 且 `"extension": true` 才算通。之后按
`SKILL.md` 第 1 节继续。

## 装不上时先看这几条

| 现象 | 原因与处理 |
|---|---|
| `ensure` 报 `"extension": false` 但扩展已加载 | 卡片上的 ID 与 host 清单里的不一致——多半加载的不是 `~/chrome-agent/extension`，或清单被改过。删掉重新加载，核对 ID |
| Chrome 更新/重启后扩展显示"已停用"或报错 | 先确认开发者模式还开着；再在 `chrome://extensions` 上重新加载扩展。host 清单不用动 |
| 更新 skill 后扩展还在跑旧代码 | `chrome-agent extension status --json` 报 `"reloadNeeded": true` 时跑 `chrome-agent extension reload`；`setup.sh` 平时会自动做掉这一步 |
| 改了仓库里的代码或说明书，机器上没变 | 两者都要重跑 `setup.sh` 才会生效——运行时是正式安装，说明书是拷贝 |
| 刚重载完，页面里某个命令没生效 | 扩展重载不影响已打开的页面；刷新该页再试 |
| 更新后扩展跑的还是 `~/.chrome-agent/extension` 那份 | 安装目录已改到 `~/chrome-agent`，旧路径不再同步。在 `chrome://extensions` 上删掉那张卡，改从 `~/chrome-agent/extension` 加载 |
| `setup.sh` 说技能目录"left alone: the checkout is already here" | 仓库被放在了技能目录里。把它挪到别处再跑 |
| `setup.sh` 拒绝覆盖技能目录 | 那里是别人的技能，不是本工具写的。确认后加 `--force` |
| `command not found: chrome-agent` | `~/.local/bin` 不在 PATH，或 `setup.sh` 没跑完 |
| `command not found: uv` | 先按上面的命令装 uv，再重跑 `setup.sh` |
| 想换扩展 ID | 正常情况下不要：清单里的 `key` 已经把 ID 固定了。确要覆盖时用 `setup.sh --extension-id <id>` |

## 卸载

```bash
<仓库目录>/setup.sh --uninstall          # 加 --purge 连 venv 和扩展副本一起删
```

扩展本身在 `chrome://extensions` 上移除。`--uninstall` 删掉 host 清单、launcher、
`~/.local/bin/chrome-agent`，以及技能目录里**它自己写的那份说明书**——若那目录不是本工具
写的，它会拒绝并说明，不会动别人的东西。`~/chrome-agent/extension` 也留着，因为已加载的
扩展正指着它——扩展移除后再删，或者用 `--purge`。
