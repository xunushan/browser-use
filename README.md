# Chrome Agent

Chrome Agent 是一个本地浏览器自动化系统，让 AI 智能体**接管用户已有的 Chrome 浏览器**（含登录会话、Cookie、扩展能力），无需启动隔离的新浏览器。

本仓库只提供**跨站**的浏览器能力；某个网站怎么采，属于那个网站自己的 skill。

---

## 目录

- [Chrome Agent](#chrome-agent)
  - [目录](#目录)
  - [项目概述](#项目概述)
    - [定位](#定位)
    - [特性](#特性)
    - [规划](#规划)
  - [安装说明](#安装说明)
    - [验证流程](#验证流程)
    - [站点授权](#站点授权)
    - [故障定位](#故障定位)
  - [系统架构](#系统架构)
    - [模块职责](#模块职责)
    - [站点能力：独立的站点 Skill](#站点能力独立的站点-skill)
  - [CLI 说明](#cli-说明)
    - [服务管理](#服务管理)
    - [常用操作](#常用操作)
  - [chrome-agent Skill](#chrome-agent-skill)
  - [许可证](#许可证)

---

## 项目概述

### 定位

解决一个核心问题：**让智能体能够操作用户已经登录的真实 Chrome**，而不是启动一个没有登录态的隔离浏览器。

V1 采用 **DOM 优先** 策略：智能体通过稳定的元素引用（ref）直接操作网页 DOM，截图接口为第二阶段的视觉能力预留。CLI 是统一入口，人和智能体共用同一套命令；登录、验证码、支付等高风险操作明确交回用户。

### 特性

- **真实浏览器接管**：复用用户现有 Chrome 的登录会话、Cookie、扩展。
- **稳定元素引用**：快照返回 `ref`，配合 `validate` 在页面变化前确认有效性。
- **懒加载图片发现与下载**：自动触发懒加载，从用户的 Chrome 会话下载到 `Downloads/chrome-agent/`。
- **站点授权机制**：权限由 Chrome 扩展系统强制执行，daemon 无权绕过；已授权的站点可以用 CLI 查看和撤销。
- **站点能力独立成 skill**：每个网站的探索流程、状态模型与产出契约放在它自己的 skill 里，本仓库不含任何站点内容。

### 规划

**V1（当前）**：DOM 优先的标签页管理、快照、点击、填写、按键、滚动、等待、提取、下载。**V2**：接入多模态视觉模型（基于 V1 已有的截图接口），并做更智能的失败恢复与跨站任务规划。

---

## 安装说明

本节的读者是**智能体**：照下面执行即可完成安装。

前置：macOS 或 Linux（Windows 未验证）、已安装 Google Chrome、[`uv`](https://docs.astral.sh/uv/)
（没有就 `curl -LsSf https://astral.sh/uv/install.sh | sh`）。

### 步骤 1：把 skill 解到技能目录

**仓库就是 skill**。归档里已经剔除了开发用的 `tests/` 与 `docs/`（`.gitattributes` 的
`export-ignore`）：

```bash
rm -rf ~/.claude/skills/chrome-agent
mkdir -p ~/.claude/skills/chrome-agent
curl -fsSL https://github.com/xunushan/chrome-agent/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 -C ~/.claude/skills/chrome-agent
```

### 步骤 2：运行 setup.sh

```bash
~/.claude/skills/chrome-agent/setup.sh
```

它一次备好运行环境（`~/chrome-agent/venv`）、Native Messaging Host、扩展 ID、扩展副本
（`~/chrome-agent/extension`）和 `chrome-agent` 命令。这一步不需要人工。

### 步骤 3：按 setup.sh 的结尾输出决定下一步

它打印什么就做什么，不要自行加戏：

| 结尾输出 | 你要做的 |
|---|---|
| `One step is left` | 请用户完成步骤 4。这是唯一需要人工的情况 |
| 已就绪 / 已经在这份拷贝上 / 已重载 | 到此为止，不要再让用户动扩展 |
| Chrome 没在运行 | 无法确认；扩展加载过就一直有效，不要打扰用户 |

### 步骤 4：请用户加载扩展

仅当步骤 3 打印 `One step is left` 时。逐字说清这四步，少一步就会失败：

1. 打开 `chrome://extensions`；
2. 打开右上角的**开发者模式**；
3. 点**加载已解压的扩展程序**；
4. 在文件选择框里进到 `~/chrome-agent`，**单击选中 `extension` 文件夹让它变蓝**，再点"打开"。

### 踩坑

- 开发者模式必须一直开着：Chrome 133 起，关掉即禁用未打包扩展。
- 步骤 4 选的是 `~/chrome-agent/extension` 这个文件夹本身；选成它的父目录会报"清单文件缺失或不可读取"。
- 扩展 ID 由清单里的 `key` 固定，不需要手动抄写或核对。
- **更新 skill 时不要重做步骤 4**：扩展加载自 `~/chrome-agent/extension`，不在 skill 目录里，
  `setup.sh` 会把新文件同步过去，并让扩展自己重载。

### 验证流程

逐层执行，每步成功后再进下一步，便于定位故障层。

**1. 验证完整连接**

```bash
chrome-agent ensure --launch-if-missing --wait-for-extension --timeout 30 --json
```

预期返回 `status=ready`、`daemon=true`、`extension=true`。

**2. 验证扩展状态**

```bash
chrome-agent extension status --json   # connected: true 即扩展在跑，reloadNeeded 看是否需要重载
```

**3. 验证标签页读取与声明**

```bash
chrome-agent tabs list --domain example.com --json
chrome-agent tabs claim 123 --json
```

预期返回当前已登录的目标标签页列表，记录要操作的 `id`。声明只确认后续操作的目标，
不会关闭、移动或重新加载用户标签页。

**4. 验证 DOM 读取**

```bash
chrome-agent page snapshot --tab-id 123 --scope full --json
```

预期包含 `documentId`、`url`、`title` 与元素数组（`ref`、`tag`、`role`、`placeholder`、
`text`、交互状态）。

### 站点授权

权限由 Chrome 扩展系统保存和强制执行，daemon 不可绕过：

- 扩展**不预置任何站点权限**，只声明 `optional_host_permissions`（`http://*/*`、
  `https://*/*`）——这是工具层的浏览器能力，不该替用户决定信任哪些站点。
- **授予**只能由用户在目标标签页点击 Chrome Agent 图标完成：`chrome.permissions.request`
  需要用户手势，CLI 给不了，所以命令面**没有** `sites grant`。**每个站点第一次都要点一次**，
  授权一次后长期有效。
- **查看与撤销**是 chrome_agent 自己的命令面：`chrome-agent sites list --json` 列出已授权站点，
  `chrome-agent sites revoke <origin>` 撤销。撤销不需要用户手势，且是幂等的。
- 扩展在注入 Content Script 前检查权限。没有目标网站权限时，扩展仍能通过 `tabs` 权限看到
  标签页标题和 URL，但不能注入 Content Script、读取或操作 DOM。

### 故障定位

| 现象 | 故障层 | 处理方式 |
| --- | --- | --- |
| 找不到 `chrome-agent` | CLI 安装或 PATH | 检查 `$HOME/.local/bin/chrome-agent` |
| `daemon=false` | daemon | 使用 `ensure --launch-if-missing` |
| `extension=false` | Native Host 或扩展 | 重新加载扩展，核对 Native Host 中的扩展 ID |
| 重启过 daemon 后一直 `No extension connected` | native host 僵留 | 旧 native host 进程还活着，扩展以为没断；重载扩展（或杀掉该进程）后恢复 |
| 能列标签页但不能 snapshot | 站点权限或 Content Script | 在目标网站授权，检查扩展错误详情 |
| `Element not found` | 引用过期 | 重新获取 snapshot |
| 操作成功但页面未变化 | 定位错误或网站事件机制 | 读取新快照，重新选择语义明确的元素 |
| 页面要求登录或验证码 | 人工交接 | 用户在 Chrome 中完成后再继续 |

想改这个 skill 而不是只用它，就把仓库 `git clone` 到技能目录（`setup.sh` 会把它软链过去，
改动立即生效）；区别只是多带了 `tests/` 与 `docs/`。卸载用 `setup.sh --uninstall`（加
`--purge` 连虚拟环境和扩展副本一起删），扩展在 `chrome://extensions` 上移除。完整说明
（各文件落在哪、装不上怎么查）见 [`references/install-and-setup.md`](references/install-and-setup.md)。

---

## 系统架构

```text
用户/智能体
    ↓ 自然语言任务
Skill
    ↓
chrome-agent CLI
    ↓ Unix Domain Socket / JSON-RPC
Daemon
    ↓ Native Messaging
Chrome 扩展（MV3 Service Worker）
    ↓ chrome.scripting
Content Script
    ↓ DOM
用户现有 Chrome 标签页
```

### 模块职责

| 模块                          | 职责                                                               |
| ----------------------------- | ------------------------------------------------------------------ |
| Skill                         | 告诉智能体何时使用 Chrome Agent、如何组合命令、如何处理登录和错误  |
| CLI                           | 将一次操作转换为结构化 RPC 并输出 JSON；无状态薄客户端             |
| Daemon                        | 长期运行的本地服务，管理扩展连接、转发请求、处理超时和请求响应关联 |
| Native Messaging Host         | 在 Chrome Native Messaging 与 daemon socket 之间全双工转发         |
| Chrome 扩展（Service Worker） | 管理标签页、检查站点权限、注入 Content Script、执行截图            |
| Content Script                | 生成 DOM 快照和元素引用；执行点击、填写、按键、滚动与提取          |

### 站点能力：独立的站点 Skill

本仓库只做跨站的那一半。某个网站怎么采——容器怎么找、滚到哪里算到底、产出什么结构——
属于那个网站自己的 skill，放在它自己的项目空间里，靠 `description` 被智能体选中，
内部读它自己的 `PLAYBOOK.md`。它与这里的唯一关系是命令面（见 [`SKILL.md` §4](SKILL.md)）：
调 `chrome-agent` 的 CLI、读 `--json` 输出，不 import `chrome_agent`、不依赖本目录的路径。
所以本站点仓库里没有、也不该有任何站点名。

---

## CLI 说明

CLI 是无状态薄客户端，把每次调用转换为一条 JSON-RPC 请求，发给本地 daemon。所有命令都支持 `--json` 输出。

### 服务管理

```bash
chrome-agent ensure --launch-if-missing   # 确保 daemon 与扩展在线
chrome-agent status                       # 查看 daemon 状态
chrome-agent start                        # 启动 daemon
chrome-agent stop                         # 停止 daemon
chrome-agent version                      # 查看版本

# 扩展：先查后装
chrome-agent extension status --json      # 装没装、连没连、是否要重载
chrome-agent extension reload             # 让扩展读一遍磁盘上的文件（免人工）
```

### 常用操作

```bash
# 站点授权：查看、撤销（授予在扩展弹窗里点，见「站点授权」）
chrome-agent sites list --json
chrome-agent sites revoke https://example.com --json

# 标签页：列出、声明、激活
chrome-agent tabs list --json
chrome-agent tabs claim <tab-id> --json
chrome-agent tabs activate <tab-id> --json

# 快照与正文
chrome-agent page snapshot --tab-id <tab-id> --scope full --json
chrome-agent page text --tab-id <tab-id> --ref <body-ref> --max-chars 20000 --json
chrome-agent page extract --tab-id <tab-id> --json

# 元素操作：点击、填写、按键、滚动、等待、校验
chrome-agent page click --tab-id <tab-id> --ref <ref> --json
chrome-agent page fill --tab-id <tab-id> --ref <ref> --value '<value>' --json
chrome-agent page keypress --tab-id <tab-id> --ref <ref> --keys Enter --json
chrome-agent page scroll --tab-id <tab-id> --ref <ref> --dy 700 --json
chrome-agent page wait --tab-id <tab-id> --selector '<stable-selector>' --timeout 10000 --json
chrome-agent page validate --tab-id <tab-id> --ref <ref> --json

# 图片与媒体：发现、触发懒加载、下载
chrome-agent page images --tab-id <tab-id> --ref <content-ref> --load --max-scrolls 12 --json
chrome-agent page download-images --tab-id <tab-id> --ref <content-ref> --load --limit 20 --prefix note --json
chrome-agent page media --tab-id <tab-id> --ref <media-ref> --json
chrome-agent page download-media --tab-id <tab-id> --ref <media-ref> --prefix note --json
```

使用约定：
- `page snapshot` 只用于定位与布局，不作为最终正文；长正文用 `page text --ref`。
- 下载成功的判据是返回中的 `state=complete` 和 `filename`，不能把"发现 URL"当作"下载完成"。

---

## chrome-agent Skill

**这个仓库就是 skill**：把它放到技能目录，智能体就能读懂该装什么、怎么装、怎么用。
所以运行时代码和扩展都在这里，不在别处——

- [`SKILL.md`](SKILL.md)：说明书。启动、操作循环、命令面、接口契约、安全交接，不含任何站点内容。
- [`references/`](references/)：按需加载的细则——[安装与配置](references/install-and-setup.md)、
  [站点 skill 规范](references/site-exploration-and-playbook-spec.md)、
  [媒体与下载](references/media-and-downloads.md)、[排错](references/troubleshooting.md)。
- [`setup.sh`](setup.sh)：配置与同步（uv 建环境、写 host 清单、把扩展同步到 `~/chrome-agent/extension`、链好 skill）；再跑一次不打扰用户，该热重载时自己热重载。
- [`chrome_agent/`](chrome_agent/)：运行时；[`extension/`](extension/)：Chrome 扩展的源码，
  实际被 Chrome 加载的是 `~/chrome-agent/extension` 那份副本。

开发时 `~/.claude/skills/chrome-agent` 是指向本仓库的软链（仓库内的 `.claude/` 不入库），
`setup.sh` 负责把它换成 `~/.claude/skills/` 与 `~/.codex/skills/`。

写新的站点 skill 前请阅读 [`references/site-exploration-and-playbook-spec.md`](references/site-exploration-and-playbook-spec.md)。

---

## 许可证

MIT
