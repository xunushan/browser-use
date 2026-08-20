# 小红书 Playbook 探索记录（2026-08-20）

## 环境

- 关键词：`稻城亚丁攻略`
- 浏览器：用户当前已登录 Chrome
- 方式：Chrome Agent DOM/ref/下载原语
- 范围：首页 Top 结果结构、图文笔记、视频笔记和当前加载评论

## 搜索页发现

- 结果卡片为 `section.note-item`；其内部 `/explore/<id>` anchor 在 DOM 中可能为 0×0 overlay。
- DOM anchor href 本身可能不含 `xsec_token`；用户真实点击产生的详情 URL 会包含访问上下文。
- 仅依据裸 href 直接导航可能进入 App-only/不可访问页。
- 当前合成点击卡片 section 没有打开详情；需点击 overlay anchor，或在 V2 用 CDP 真实输入事件。
- 已给零尺寸 anchor 增加可见父容器 rect 回退，待扩展重载后回归。

## 图文样例

- 类型：图片轮播
- 页面提示：`1/11`
- 结构：`note-container → xhs-slider-container`，正文为 `note-text`，评论为 `comments-el`
- 正文：331 字，`truncated=false`
- 当前加载评论：794 字；页面显示评论总数，但折叠回复未保证全部展开
- 目标媒体：11 张 WebP
- 下载：11/11 `state=complete`
- 下载目录：用户 Chrome 默认下载目录的 `chrome-agent/` 子目录
- 发现：首次 scoped images 可在懒加载前为空，而 download 阶段发现 11 张；collector 已回填下载阶段 URL。

## 视频样例

- 类型：16:09、1920×1080 视频
- 结构：`video-player-media/player-container`，正文为 `note-text`，评论为 `comments-el`
- 正文：677 字，`truncated=false`
- 当前加载评论：621 字；页面显示 34 条评论，未保证回复全部展开
- scoped `<video>.currentSrc`：`blob:`，不可作为文件下载 URL
- page-level JSON-LD：`VideoObject.contentUrl`，direct signed MP4
- 下载：1/1 `state=complete`
- 文件：`Downloads/chrome-agent/6a7077080000000033012701-001.mp4`
- 结论：播放器 scoped discovery 与 page-level structured data 必须合并。

## 已验证 CLI 链路

```text
snapshot → text(body ref)
snapshot/scroll → text(comments ref)
images(slider ref) → download-images(slider ref)
media(player ref) + media(page) → download-media(page)
```

## 未完成自动化闭环

- 搜索卡片的 overlay anchor 真实点击回归；
- 自动点击并展开所有评论回复；
- 搜索首页每条 Top 结果的批量循环；
- 虚拟化轮播逐页点击（本图文样例已一次发现全部 11 张）；
- blob/HLS/DASH 下载。

这些限制必须由 Playbook 明确报告，不能把“当前已加载评论”描述为“全部评论”，也不能把裸 `/explore/<id>` 当作可复用详情 URL。

