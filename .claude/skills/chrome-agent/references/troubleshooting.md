# 故障排查（通用）

按现象查。这里只写工具层面的失效模式，站点自己的恢复流程（例如"评论没到底怎么办"）在该站点的 `PLAYBOOK.md` 里。

## ref 用不了了

`page validate` 会直接告诉你原因：

```bash
chrome-agent page validate --tab-id <tab-id> --ref <ref> --json
```

| `error` | 发生了什么 | 怎么办 |
|---|---|---|
| `Element not found` | 这个 ref 从来不属于当前文档（页面已导航/刷新，注册表已被替换） | 重新 snapshot |
| `Element no longer in DOM` | 元素被移除 | 重新 snapshot，找替代元素 |
| `Element not visible` | 元素还在，但不可见（折叠、被遮挡、滚出屏幕外） | 先滚动/展开，或换一个可见的等价元素 |
| `Element is disabled` | 控件被禁用 | 等页面状态变化，或换路径 |

同一个元素在多次快照之间 ref 不变，所以一个 ref 可以跨几步继续用；一旦重渲染，就该重新取。**不要**缓存上一次的 ref 跨页面使用。

## 快照里找不到目标

`page snapshot` 返回 `matched`（匹配到的总数）和 `truncated`（是否被截断），先看这两个字段：

```bash
chrome-agent page snapshot --tab-id <tab-id> --scope full --limit 3000 --json
```

- `truncated: true` → 有元素被丢掉了。快照是"按屏幕纵向位置排序后取前 N 个"，默认 N=500（`--limit 0` 表示不设上限）。被丢掉的是排序靠后的那部分。
- 目标确实在页面上但不在快照里 → 调大 `--limit`，或先用 `--scope viewport` 缩小范围，或先滚动到目标附近再取快照。
- 元素存在但没有任何文本、也不可交互，按设计不会进快照（快照只收可交互或有文本的元素）。这类元素只能靠父容器定位。

## 页面在后台不推进

Chrome 会对后台标签页降频：定时器、事件循环、媒体播放都会被节流，于是"页面自己会继续加载"的内容（无限滚动、分批追加的列表、播放器）在后台就停住了。表现是：明明在滚动，内容却不再变多。

```bash
chrome-agent tabs activate <tab-id> --json
```

让标签页可见之后再操作，可见布局相关的命令（视口截图、当前视口范围、依赖真实滚动的懒加载）同样需要它。

## 连不上浏览器

| 现象 | 处理 |
|---|---|
| `Daemon socket not found` | 守护进程没起来：`chrome-agent start`（或 `chrome-agent ensure --launch-if-missing --wait-for-extension --timeout 30`） |
| `No extension connected` | 守护进程在跑，但扩展没注册：确认 Chrome 打开且扩展已加载；扩展重新注册可能需要几十秒 |
| 转发报错里提到扩展端口/消息通道关闭，例如 `... moved into back/forward cache, so the message channel is closed.` | 目标标签页在后台被冻结了：`tabs activate` 后重试；这是一次传输失败，不是页面失败，重试同样的操作即可 |

`chrome-agent status --json` 可以先看服务、守护进程、扩展各自的连接状态，比逐个试命令快。

## 滚动没反应

`page scroll` 返回 `moved`；`moved=false` 就是没滚动。

- 不给 `--ref` 时滚的是"页面上最大的可见滚动容器"，未必是你想动的那个。给一个位于目标区域内、且最近的可滚动祖先就是目标容器的元素 ref。
- 刚打开或刚切换状态时，容器可能还没布局完，第一次滚动会报没动。稍等再试一次，别据此判"到底了"。
- 页面用虚拟滚动（只保留视口内的节点）时，滚动位置变了但元素节点会被换掉：所有旧 ref 作废，要重新取快照。

## 长文本不完整

`page text` 的返回里 `truncated` 为真就说明被 `--max-chars` 截断了（上限 200000）。另外 `page snapshot` 里元素的文本上限是 200 字符——那是定位用的，**不是正文**。

- 优先取更精确的容器（正文块本身，而不是包着导航/评论/推荐的外层容器）。
- 调到上限仍不够，就分段读（按子块 ref 分别读），并如实报告内容被切分过。

## 内容取不到 / 需要登录

页面说"内容暂时无法查看"、"请在 App 内查看"，或要求登录、验证码、扫码、确认时：

- 如实报告这个状态，继续处理其他可访问的目标；
- 不要尝试绕过登录、验证码、风控、内容保护；
- 需要用户操作时停下来交接，并说清需要用户在哪一步做什么。

## 下载失败

见 [media-and-downloads.md](media-and-downloads.md) 的"判成功"一节。简言之：`state=complete` + `filename` 才算成功，其余（`interrupted`/`failed`/`in_progress`）都要逐项报告，`error` 字段是浏览器给的原因。
