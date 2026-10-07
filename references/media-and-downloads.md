# 媒体发现与下载（通用）

适用于任何站点。站点自己的容器、点击流程、去重规则放该站点的 `PLAYBOOK.md`。

## 命令与关键参数

```bash
# 发现图片（不下载）：currentSrc、srcset、<source srcset>、CSS 背景图
chrome-agent page images --tab-id <tab-id> [--ref <container-ref>] [--load] \
  [--max-scrolls 12] [--settle-ms 500] --json

# 下载图片：默认 20 张，上限 100
chrome-agent page download-images --tab-id <tab-id> [--ref <container-ref>] \
  [--url <exact-url> ...] [--limit 20] [--load] [--timeout 30] [--prefix image] --json

# 发现视频/音频资源（含不可直链的）
chrome-agent page media --tab-id <tab-id> [--ref <media-container-ref>] --json

# 下载可直接下载（downloadable=true）的媒体：默认 10，上限 50
chrome-agent page download-media --tab-id <tab-id> [--ref <container-ref>] \
  [--limit 10] [--timeout 120] [--prefix media] --json
```

- `--url` 可重复；它是一份白名单，且只接受 `--ref` 作用域内已发现的 URL（作用域外的 URL 会被丢弃）。
- `--load` 会滚动页面来触发懒加载，这是有副作用的动作：页面位置会变，之后的 ref 需要重新取。
- `--timeout` 是单个文件的等待秒数；大文件（视频）要调大，超时会返回 `in_progress` + `timedOut`。

## 先发现，再下载

两步走，不要直接下：

1. `page images` / `page media` 拿到候选，逐个看清 URL、尺寸、`source`、`type`、`downloadable`。
2. 只把确认属于目标内容的 URL 交给下载命令。容器里一旦混入头像、图标、表情、评论配图或推荐位，`--limit` 会照单全收；显式 `--url` 白名单是唯一能挡住它的东西。

## 作用域取最窄的那个容器

`--ref` 决定"这一片里所有的图/媒体"。留空就是整个文档，会把背景页、导航图标、推荐位一起收进来。

- 从一次新的全量快照里挑那个恰好包住目标内容的容器（弹层、媒体列表、播放器、正文块），而不是最外层的模态或整页容器。
- 作用域越窄，"这里面的一切都是目标内容"这个判断越可靠；只有拿不准的回退作用域才需要按 URL 特征过滤。

## 判成功

一次下载成功 = 该项 `state=complete` **且**有 `filename`。除此之外都不算：

| 返回 | 含义 |
|---|---|
| `complete` + `filename` | 成功，文件已在 `Downloads/chrome-agent/` 下 |
| `in_progress` / `timedOut: true` | 到超时还没完，加大 `--timeout` 或稍后确认 |
| `interrupted` / `failed` + `error` | 失败，`error` 是浏览器给的原因 |
| 只出现在 `images`/`audioVideo`/`unsupported` 里 | **只是发现**，一个字节都没下 |

必须逐项报告成功的文件名和所有失败项；"发现了 URL"不能写成"已下载"。

## 通用陷阱

- **`page screenshot` 不是下载手段**。它给的是可见视口的像素，还要额外的活动标签页权限；要拿图片资源本身只能用 `page images` / `download-images`。截图可以做视觉证据，不能当产物。
- **按完整 URL 去重，保留 query**。响应式 `srcset` 会给同一张图多个 URL，虚拟化列表会复用同一个节点。签名参数也常在 query 里，去掉就取不到。
- **`blob:` 不是资源**。用了 MSE/EME 的播放器只暴露 `blob:`；同一个页面的结构化数据（例如 JSON-LD `VideoObject`）里往往同时有可直链的地址。两边都看，别只看播放器子树。
- **HLS/DASH/DRM 属于能力缺口**。返回 `hls`/`dash`/`unsupported`/`missing` 时如实报告"需要流媒体支持"，不要去绕 DRM 或访问控制。
- **同一容器里的图不一定同源**。头像、表情、图标常与内容图共用 CDN 域名和尺寸，尺寸阈值区分不了它们——区分靠容器和作用域，不靠尺寸。
- **下载落在用户的浏览器里**。用的是用户已登录的 Chrome profile，文件进的是 Chrome 的正常下载目录；下载前确认用户确实要这些文件。
