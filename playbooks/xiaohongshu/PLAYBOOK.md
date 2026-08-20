# 小红书内容下载 Playbook

适用站点：`xiaohongshu.com`（包括其子域名）

这是智能体下载小红书笔记时的唯一站点入口。执行前先阅读本文件；探索新网站时阅读 Chrome Agent Skill 引用的 `references/site-exploration-and-playbook-spec.md`。

## 目标与非目标

使用当前已登录 Chrome 搜索小红书，处理首页结果中的可访问笔记，提取正文、当前已加载评论，并下载目标图片或 direct 视频。不得绕过 App-only、验证码、风控、登录和内容保护。

## 页面状态模型

```text
SEARCH → RESULT_READY → DETAIL_OPEN
DETAIL_OPEN → IMAGE_NOTE / VIDEO_NOTE
DETAIL_OPEN → BODY_READY → COMMENTS_READY
任意状态 → APP_ONLY / LOGIN_HANDOFF / ACCESS_DENIED / REF_STALE
```

## 语义识别规则

| 目标 | 首选关系 | class 弱提示 |
|---|---|---|
| 搜索框 | input + 搜索语义 | `search-input` |
| 结果卡片 | 标题/作者 + `/explore/` anchor | `note-item` |
| 详情 | 覆盖背景且包含正文/媒体/评论 | `note-detail-mask`, `note-container` |
| 正文 | 详情内最窄长文本容器 | `note-text` |
| 图片 | 详情内带页码的媒体容器 | `xhs-slider-container` |
| 视频 | 内含 video 和播放器控制 | `video-player-media`, `player-container` |
| 评论 | 详情交互区评论总容器 | `comments-el` |

class 不是固定 selector，运行时必须结合可见区域、容器关系、文字和元素类型重新判断。

## 小红书链接访问上下文

小红书详情链接可能携带 `xsec_token`、`xsec_source` 等访问上下文。智能体不得从笔记 ID 自行拼接、缩短或清除这些参数；优先点击搜索结果中的实时 ref。若必须导航，只能原样使用当前页面发现的完整 href。没有 `xsec_token` 的裸 `/explore/<id>` 链接不应被视为可长期复用的详情 URL。

## 标准工作流

1. 在搜索结果页执行 `scripts/discover.py`，得到候选结果的实时 `ref` 和完整 `href`。
2. 智能体验证并点击其中一个结果 ref；直接导航时原样使用当前页面发现的完整 href。
3. 详情打开后重新 snapshot，智能体识别正文、媒体、评论的最窄实时 ref。
4. 智能体把这些 ref 传给 `scripts/collect.py`，由脚本做固定的提取、下载、去重和 JSON 输出。
5. 返回结果页后重新 snapshot，再处理下一条；所有旧 ref 作废。

## 脚本入口：何时使用、如何使用

脚本由智能体调用，用户通常只需提出任务，不需要手动填写 ref。它们不替代智能体的页面理解：`ref` 会在页面刷新、打开详情或切换轮播后失效，必须由智能体从**当次** snapshot 重新解析。

| 脚本 | 使用时机 | 输入 | 输出 | 不负责的事 |
|---|---|---|---|---|
| `scripts/discover.py` | 已完成搜索、当前处于结果页时 | `tab-id`、候选数量 | `/explore/` 候选的 rank、ref、href | 不点击、不打开详情、不保证裸 href 可访问 |
| `scripts/collect.py` | 已打开一条详情，且智能体刚从 snapshot 找到正文/评论/媒体 ref 时 | `tab-id` 和实时 ref，选择是否下载图片/视频 | 单条笔记 JSON、下载状态、文件名 | 不搜索、不猜 ref、不绕过 App-only/验证码/登录 |

### 1. 结果页：发现候选笔记

智能体先在当前搜索结果 tab 运行：

```bash
python playbooks/xiaohongshu/scripts/discover.py --tab-id <search-tab-id> --limit 10
```

脚本仅把 full snapshot 中的候选 anchor 结构化输出。智能体应优先用返回的 `ref` 点击；如果结果里 `hasAccessContext=false`，不能把裸 href 当成永久可访问链接，仍应优先点击页面元素并观察详情是否成功打开。

### 2. 详情页：收集一条笔记

智能体打开详情后，先执行 `chrome-agent page snapshot --scope full`，找到 `body-ref`，以及按笔记类型选择图片轮播的 `images-ref` 或视频播放器的 `media-ref`；需要评论时同时提供 `comments-ref`。随后运行：

```bash
python playbooks/xiaohongshu/scripts/collect.py \
  --tab-id <detail-tab-id> \
  --body-ref <note-text-ref> \
  --comments-ref <comments-ref> \
  --images-ref <slider-ref> \
  --comment-scrolls 3 \
  --download-images \
  --prefix <note-id> \
  --output-dir outputs/xiaohongshu/<note-id>
```

视频笔记将 `--images-ref ... --download-images` 换成 `--media-ref <player-ref> --download-media`。图文和视频都可以保留评论参数。`--output-dir` 会生成统一的笔记目录：`note.json` 放正文、评论和下载记录，图片放 `images/`，视频放 `videos/`。脚本会只下载已发现且符合笔记原图特征的 URL；`downloads` 中必须逐项为 `state=complete` 才算下载成功。

兼容旧用法的 `--output <json-path>` 仍可使用，但媒体会放在该 JSON 同级的 `images/`、`videos/` 目录；新任务应优先使用 `--output-dir`，避免不同笔记的媒体混放。

如页面发生重渲染、脚本提示 ref 不存在、内容为 App-only 或下载候选为空，停止复用旧 ref，回到 snapshot 与页面状态判断步骤；不要让脚本猜测选择器。

## 正文与评论

```bash
chrome-agent page text --tab-id <id> --ref <body-ref> --max-chars 20000 --json
chrome-agent page scroll --tab-id <id> --ref <comments-ref> --dy 700 --json
chrome-agent page text --tab-id <id> --ref <comments-ref> --max-chars 100000 --json
```

评论仅代表 Web 页面当前滚动/展开后已加载的内容。`note.json` 的 `comments.items` 是 `{author, text}` 记录；时间/地区、点赞、回复按钮、回复展开提示和作者徽标等 UI 元数据不会写入每条评论，完整页面原始文本保留在 `comments.rawText`。需要更多评论时，智能体先点击“展开 N 条回复”，滚动评论容器直到无新增或达到任务限制，再解析新 ref。

## 图片与视频

```bash
chrome-agent page images --tab-id <id> --ref <slider-ref> --json
chrome-agent page download-images --tab-id <id> --ref <slider-ref> --url '<已核验图片 URL>' --prefix <note-id> --json
chrome-agent page media --tab-id <id> --ref <player-ref> --json
chrome-agent page download-media --tab-id <id> --ref <player-ref> --prefix <note-id> --json
```

虚拟轮播按 Skill 流程逐页点击并去重。本次视频探索样例同时暴露 `<video>` 和 JSON-LD `VideoObject.contentUrl`，direct MP4 可下载；blob/HLS/DASH 只报告。

图片必须先通过 `page images --ref <slider-ref> --load` 发现并核验，再传 URL 白名单下载；不得对 `note-container`、评论容器或整页直接 `download-images --limit`，否则会下载表情、头像或推荐卡片的小图。

播放器容器内的 `<video>` 可能只暴露 `blob:`，而 direct MP4 位于页面级 JSON-LD。因此先用 scoped media 确认目标播放器，再执行一次不带 ref 的 page-level media discovery；按当前笔记、类型、时长和结构化数据关联 direct URL。不得把 blob URL 当作文件下载地址。

## 完成条件

- 来源 URL 保留访问参数；正文未静默截断；
- 评论说明是否可能不完整；
- 下载逐项返回 `state=complete` 和 filename；
- 输出符合 Schema；背景结果、头像、图标未混入媒体。

## 失败恢复和限制

- ref 失效：重新 full snapshot；URL 过期：重新发现媒体；
- App-only/风控：记录并跳过，不绕过；
- 评论回复展开和虚拟轮播仍由智能体根据实时 DOM 编排；
- 首页 Top 由网站当次排序决定，不假设固定结果。

## 验证用例

- 关键词：`稻城亚丁攻略`；
- 图文：正文、轮播、评论；视频：direct MP4、正文、评论；
- 失败：App-only、缺失或过期 `xsec_token`。

本次真实探索证据见 `fixtures/exploration-2026-08-20.md`。
