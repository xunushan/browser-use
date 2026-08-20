# Chrome Agent 验证流程与控制链路

## 1. 文档目的

本文说明 Chrome Agent V1 的控制链路、人工验证步骤和智能体验收方法。核心结论是：

- 前四步由开发者或用户手动调用 CLI，逐层确认底层能力。
- 第五步由智能体读取 Skill 后自主组合相同的 CLI 命令。
- 人工控制和智能体控制使用同一条底层链路，区别仅在于 CLI 的调用者。

## 2. 系统控制链路

```text
用户自然语言任务
        ↓
智能体读取 Chrome Agent Skill
        ↓
chrome-agent CLI
        ↓ Unix Domain Socket / JSON-RPC
Chrome Agent daemon
        ↓ Native Messaging Host
Chrome 扩展 Service Worker
        ↓ chrome.tabs / chrome.scripting
Content Script
        ↓ DOM
用户现有 Chrome 标签页
```

结果沿相反方向返回：

```text
网页执行结果或 DOM 数据
        ↑
Content Script
        ↑
Chrome 扩展
        ↑
Native Messaging Host
        ↑
daemon
        ↑
CLI JSON 输出
        ↑
人工检查或智能体推理
```

## 3. 各组件职责

| 组件 | 主要职责 | 不负责的事情 |
|---|---|---|
| Skill | 告诉智能体何时使用 Chrome Agent、如何组合命令、如何处理登录和错误 | 不直接操作 Chrome |
| CLI | 将一次操作转换为结构化 RPC，并输出 JSON | 不保存浏览器状态，不理解用户目标 |
| daemon | 管理扩展连接、转发请求、处理超时和请求响应关联 | 不直接访问网页 DOM |
| Native Messaging Host | 在 Chrome Native Messaging 与 daemon socket 之间进行全双工转发 | 不规划任务，不处理网页业务 |
| Chrome 扩展 | 管理标签页、检查站点权限、注入 Content Script、执行截图 | 不理解自然语言任务 |
| Content Script | 生成 DOM 快照和元素引用，执行点击、填写、按键、滚动与提取 | 不读取 Cookie、密码库或浏览器历史 |
| 智能体 | 理解目标、选择标签页和元素、决定下一步、整理结果 | 不直接调用 Chrome API |

## 4. 人工验证流程

人工验证采用逐层方式。每一步成功后再进行下一步，便于快速定位故障层。

### 第一步：验证完整连接

```bash
chrome-agent ensure \
  --launch-if-missing \
  --wait-for-extension \
  --timeout 30 \
  --json
```

预期结果：

```json
{
  "status": "ready",
  "daemon": true,
  "chrome": true,
  "extension": true
}
```

该步骤验证：

```text
CLI → daemon → Native Host → Chrome 扩展
```

若 `daemon` 为 `false`，检查 CLI 安装和 daemon 启动；若 `extension` 为 `false`，检查扩展是否启用、Native Host 配置是否匹配扩展 ID，并重新加载扩展。

### 第二步：验证标签页读取

先在 Chrome 中打开目标网站，例如小红书，然后执行：

```bash
chrome-agent tabs list --domain xiaohongshu.com --json
```

预期返回一个或多个标签页：

```json
{
  "tabs": [
    {
      "id": 123,
      "url": "https://www.xiaohongshu.com/",
      "title": "小红书",
      "active": true
    }
  ]
}
```

该步骤验证 daemon 能向扩展发送命令，并能收到 `chrome.tabs` 返回的数据。记录目标标签页的 `id`。

### 第三步：验证标签页声明

```bash
chrome-agent tabs claim 123 --json
```

预期返回目标标签页的 ID、URL 和标题。声明操作不会关闭、移动或重新加载用户标签页，它只确认后续操作的目标。

### 第四步：验证 DOM 读取

```bash
chrome-agent page snapshot \
  --tab-id 123 \
  --scope full \
  --json
```

预期结果包含：

- `documentId`
- 当前 `url` 和 `title`
- `elements` 数组
- 元素的 `ref`、`tag`、`role`、`placeholder`、`text` 和交互状态

该步骤验证：

```text
扩展 → Content Script 注入 → DOM 快照 → 原路返回 CLI
```

如果返回站点未授权错误，应在目标标签页点击 Chrome Agent 图标并授权当前网站。站点授权由 Chrome 的扩展权限系统保存和强制执行，不是 daemon 的授权列表。

## 5. 智能体验收流程

前四步成功后，底层控制能力已经确认。第五步只把 CLI 调用者从人工换成智能体。

示例任务：

```text
使用 Chrome Agent 操作我当前已登录的 Chrome，在小红书搜索“稻城亚丁攻略”，
提取前五条搜索结果的标题和来源链接并汇总。只使用 DOM，不使用视觉能力；
遇到登录或验证码就暂停。
```

智能体应执行以下逻辑：

1. 调用 `ensure` 检查完整链路。
2. 调用 `tabs list` 查找可复用的目标标签页。
3. 调用 `tabs claim` 声明目标。
4. 调用 `page snapshot` 获取当前文档和元素引用。
5. 根据 `role`、名称、标签、placeholder 和附近文本选择搜索框。
6. 调用 `page validate` 确认引用仍然有效。
7. 调用 `page fill` 输入搜索词。
8. 调用 `page keypress` 或 `page click` 提交搜索。
9. 调用 `page wait` 等待导航或结果元素出现。
10. 页面变化后重新调用 `page snapshot`，不复用旧文档的元素引用。
11. 调用 `page extract` 提取所需数量的标题和来源链接。
12. 在对话中汇总，并明确区分页面原始信息与智能体归纳。

搜索结果链接可能包含站点签发的访问上下文参数。智能体应优先点击搜索结果 `ref`；如果需要调用 `tabs open` 或 `tabs navigate`，必须使用快照或提取结果中的完整绝对 `href`，不能根据内容 ID 重建 URL，也不能删除 `xsec_token`、签名、来源或过期时间等查询参数。

若任务包含图片，可在详情页执行：

```bash
chrome-agent page images --tab-id 123 --load --max-scrolls 12 --json
chrome-agent page download-images --tab-id 123 --load --limit 20 --prefix note --json
```

下载文件进入 Chrome 默认下载目录的 `chrome-agent/` 子目录。智能体必须根据返回的 `state=complete` 和 `filename` 判断成功，不能把“发现图片 URL”当作“下载完成”。

## 6. 元素引用与页面变化

DOM 快照中的 `ref` 只属于生成它的 `documentId`。以下情况发生后，应丢弃旧引用并重新获取快照：

- 页面导航或刷新
- 单页应用完成主要页面切换
- 搜索结果重新渲染
- DOM 大范围更新
- 元素已被替换或移除

正确循环是：

```text
snapshot → 选择 ref → validate → 操作 → 检查变化 → 新 snapshot
```

这可以减少页面变化后点击错误元素的风险。

## 7. 站点授权逻辑

站点权限来自 Chrome 扩展 manifest 和 `chrome.permissions` API：

- `host_permissions` 是扩展加载时获得的固定权限。
- `optional_host_permissions` 需要用户通过扩展弹窗主动授权。
- Chrome 保存并强制执行权限。
- 扩展在注入 Content Script 前检查权限。
- daemon 只转发操作，不保存网站授权名单，也不能绕过 Chrome 权限。

没有目标网站权限时，扩展仍可能通过 `tabs` 权限看到标签页标题和 URL，但不能向页面注入 Content Script，也不能读取或操作 DOM。

## 8. 安全边界与人工交接

遇到以下场景时，智能体应暂停并交给用户：

- 用户名、密码登录
- 二维码扫码
- 短信验证码或一次性验证码
- CAPTCHA
- 支付、发布、删除或权限变更
- 网站安全警告或风险确认

系统不读取或导出 Cookie、Local Storage、密码库、验证码和浏览器历史。V1 只根据 DOM 工作，不根据截图像素作判断。

## 9. 验收标准

满足以下条件，可以认为 V1 主链路验收通过：

- `ensure` 返回 `status=ready` 且 `extension=true`
- 能列出用户当前 Chrome 标签页
- 能声明目标标签页
- 能获取目标网站的 DOM 快照
- 能根据语义找到并操作页面元素
- 页面变化后能刷新元素引用
- 能提取真实页面信息和来源 URL
- 智能体能够自主组合通用 CLI 命令完成任务
- 登录、验证码和高风险操作能够正确交给用户
- 没有启动与用户 Profile 隔离的新浏览器

## 10. 故障定位

| 现象 | 可能故障层 | 检查方式 |
|---|---|---|
| 找不到 `chrome-agent` | CLI 安装或 PATH | 检查 `$HOME/.local/bin/chrome-agent` |
| `daemon=false` | daemon | 使用 `ensure --launch-if-missing` |
| `extension=false` | Native Host 或扩展 | 重新加载扩展，核对 Native Host 的扩展 ID |
| 能列标签页但不能 snapshot | 站点权限或 Content Script | 在目标网站授权，检查扩展错误详情 |
| `Element not found` | 引用过期 | 重新获取 snapshot |
| 操作成功但页面未变化 | 定位错误或网站事件机制 | 读取新快照，重新选择语义明确的元素 |
| 页面要求登录或验证码 | 人工交接 | 用户在 Chrome 中完成后再继续 |

## 11. 当前阶段范围

V1 支持 DOM 优先的标签页管理、快照、点击、填写、按键、滚动、等待、提取和截图保存。截图只作为第二阶段视觉能力的预留接口；V1 不声称理解图片或像素内容。
