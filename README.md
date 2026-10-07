# Chrome Agent

Chrome Agent 是一个本地浏览器自动化系统，让 AI 智能体能够**接管用户已有的 Chrome 浏览器**（含登录会话、Cookie、扩展能力），无需启动隔离的新浏览器。

V1 阶段采用 **DOM 优先** 策略：智能体通过稳定的元素引用直接操作网页 DOM，截图接口作为第二阶段视觉模型的预留接入点。

---

## 目录

- [Chrome Agent](#chrome-agent)
  - [目录](#目录)
  - [项目概述](#项目概述)
    - [定位](#定位)
    - [特性](#特性)
    - [规划](#规划)
  - [系统架构](#系统架构)
    - [模块职责](#模块职责)
    - [站点沉淀：Playbook](#站点沉淀playbook)
  - [安装说明](#安装说明)
    - [安装步骤](#安装步骤)
    - [验证流程](#验证流程)
    - [站点授权](#站点授权)
    - [故障定位](#故障定位)
  - [CLI 说明](#cli-说明)
    - [服务管理](#服务管理)
    - [常用操作](#常用操作)
  - [chrome-agent Skill](#chrome-agent-skill)
  - [许可证](#许可证)

---

## 项目概述

### 定位

解决一个核心问题：**让智能体能够操作用户已经登录的真实 Chrome**，而不是启动一个没有登录态的隔离浏览器。

设计原则：

- **DOM 优先**：用稳定的元素引用（ref）操作页面，截图接口只为第二阶段视觉能力预留。
- **人工与智能体共用底层**：CLI 是统一入口，调用者既可以是人也可以是智能体。
- **安全边界明确**：登录、验证码、支付等高风险操作明确交给用户。
- **通用能力 + 站点沉淀**：跨站通用能力由 CLI / Skill 提供，网站特定流程沉淀在 Playbook。

### 特性

- **真实浏览器接管**：复用用户现有 Chrome 的登录会话、Cookie、扩展。
- **稳定元素引用**：快照返回 `ref`，配合 `validate` 在页面变化前确认有效性。
- **懒加载图片发现与下载**：自动触发懒加载，从用户的 Chrome 会话下载到 `Downloads/chrome-agent/`。
- **站点授权机制**：权限由 Chrome 扩展系统强制执行，daemon 无权绕过。
- **Playbook 沉淀**：每个网站可沉淀独立的探索流程、状态模型、脚本与契约。

### 规划

- **V1（当前）**：DOM 优先的标签页管理、快照、点击、填写、按键、滚动、等待、提取、下载。
- **V2**：多模态视觉模型接入（基于 V1 已有截图接口）；更智能的失败恢复与跨站任务规划。

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

### 站点沉淀：Playbook

Chrome Agent 的通用接口只解决跨站能力，**特定网站的具体流程沉淀在 [`playbooks/<site>/`](playbooks/)**（参考现有 [`playbooks/xiaohongshu/`](playbooks/xiaohongshu/)），由智能体在跑该网站时读取执行。

---

## 安装说明

### 安装步骤

1. 打开 `chrome://extensions`，启用开发者模式。
2. 选择"加载已解压的扩展程序"，加载项目中的 `extension/` 目录。
3. 复制 Chrome 显示的 32 位扩展 ID，运行：

   ```bash
   ./install.sh <扩展ID>
   ```

   该脚本一次性安装 CLI / daemon / Native Messaging Host，并把 `.claude/skills/chrome-agent` 链接到 `~/.claude/skills/` 与 `~/.codex/skills/`。

4. 在 `chrome://extensions` 重新加载扩展。

小红书已预授权；操作其他网站前，用户需在目标标签页点击 Chrome Agent 图标并授权当前网站。

### 验证流程

逐层执行，每步成功后再进下一步，便于定位故障层。

**1. 验证完整连接**

```bash
chrome-agent ensure \
  --launch-if-missing \
  --wait-for-extension \
  --timeout 30 \
  --json
```

预期返回 `status=ready`、`daemon=true`、`extension=true`。

**2. 验证标签页读取**

在 Chrome 中打开目标网站后执行：

```bash
chrome-agent tabs list --domain xiaohongshu.com --json
```

预期返回当前已登录的目标标签页列表，记录要操作的 `id`。

**3. 验证标签页声明**

```bash
chrome-agent tabs claim 123 --json
```

声明只确认后续操作的目标，不会关闭、移动或重新加载用户标签页。

**4. 验证 DOM 读取**

```bash
chrome-agent page snapshot --tab-id 123 --scope full --json
```

预期包含 `documentId`、`url`、`title`、元素数组（`ref`、`tag`、`role`、`placeholder`、`text`、交互状态）。

### 站点授权

权限由 Chrome 扩展系统保存和强制执行，daemon 不可绕过：

- `host_permissions`：扩展加载时获得的固定权限。
- `optional_host_permissions`：需要用户通过扩展弹窗主动授权。
- 扩展在注入 Content Script 前检查权限。
- 没有目标网站权限时，扩展能通过 `tabs` 权限看到标签页标题和 URL，但不能注入 Content Script、读取或操作 DOM。

### 故障定位

| 现象                      | 故障层                    | 处理方式                                   |
| ------------------------- | ------------------------- | ------------------------------------------ |
| 找不到 `chrome-agent`     | CLI 安装或 PATH           | 检查 `$HOME/.local/bin/chrome-agent`       |
| `daemon=false`            | daemon                    | 使用 `ensure --launch-if-missing`          |
| `extension=false`         | Native Host 或扩展        | 重新加载扩展，核对 Native Host 中的扩展 ID |
| 能列标签页但不能 snapshot | 站点权限或 Content Script | 在目标网站授权，检查扩展错误详情           |
| `Element not found`       | 引用过期                  | 重新获取 snapshot                          |
| 操作成功但页面未变化      | 定位错误或网站事件机制    | 读取新快照，重新选择语义明确的元素         |
| 页面要求登录或验证码      | 人工交接                  | 用户在 Chrome 中完成后再继续               |

---

## CLI 说明

CLI 是无状态薄客户端，把每次调用转换为一条 JSON-RPC 请求，发给本地 daemon。所有命令都支持 `--json` 输出。

### 服务管理

```bash
chrome-agent ensure --launch-if-missing   # 确保 daemon 与扩展在线
chrome-agent status                       # 查看状态
chrome-agent start                        # 启动 daemon
chrome-agent stop                         # 停止 daemon
chrome-agent version                      # 查看版本
```

### 常用操作

```bash
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

`.claude/skills/chrome-agent/` 是智能体侧的入口文件，告诉智能体如何组合 CLI 完成常见任务（浏览、搜索、点击、填写、滚动、提取、下载）。

智能体在接手浏览器自动化任务时应自动加载该 Skill；处理特定网站时再加载对应的 [`playbooks/<site>/`](playbooks/)。

完整内容见 [`.claude/skills/chrome-agent/SKILL.md`](.claude/skills/chrome-agent/SKILL.md)；新建或更新 Playbook 前请阅读 [`.claude/skills/chrome-agent/references/site-exploration-and-playbook-spec.md`](.claude/skills/chrome-agent/references/site-exploration-and-playbook-spec.md)。

---

## 许可证

MIT