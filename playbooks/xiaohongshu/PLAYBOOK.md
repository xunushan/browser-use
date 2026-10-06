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
| 结果卡片 | 带访问上下文的 `/search_result/<id>` 可见 cover anchor | `note-item`, `cover mask` |
| 详情 | 覆盖背景且包含正文/媒体/评论 | `note-detail-mask`, `note-container` |
| 正文 | 详情内最窄长文本容器 | `note-text` |
| 图片 | 详情内带页码的媒体容器 | `xhs-slider-container` |
| 视频 | 内含 video 和播放器控制 | `video-player-media`, `player-container` |
| 评论 | 详情交互区评论总容器 | `comments-container`（外层 `comments-el`） |

这些 class 是 `locators.yaml` 中的弱提示，不是脚本内联 selector；运行时仍须结合可见区域、容器关系、文字和元素类型重新判断。

## 小红书链接访问上下文

小红书详情链接可能携带 `xsec_token`、`xsec_source` 等访问上下文。智能体不得从笔记 ID 自行拼接、缩短或清除这些参数；优先点击搜索结果中的实时 ref。若必须导航，只能原样使用当前页面发现的完整 href。没有 `xsec_token` 的裸 `/explore/<id>` 链接不应被视为可长期复用的详情 URL。

## 标准工作流

1. 在搜索结果页执行 `scripts/discover.py`，得到候选结果的实时 `ref`、`noteId`、标题和完整 `href`。
2. 智能体用 `--open-rank` 打开候选；若已有详情遮罩，脚本先关掉它（见下）。`--open-rank` 会**核验落点**：点完轮询 URL 与详情标记（`detail.open_markers`），只有确认落在目标 `noteId` 上才返回成功；点不中时自动退回 `--open-mode navigate`，两条路都不中则报错退出，不会把上一条笔记当成本次结果。当前页不是搜索结果页时同样报错并给出实际 URL，而不是返回空候选。
3. 详情打开后重新 snapshot，智能体识别正文、媒体、评论的最窄实时 ref。
4. 智能体把这些 ref 传给 `scripts/collect.py`，由脚本做固定的提取、下载、去重和 JSON 输出。
5. 返回结果页后重新 snapshot，再处理下一条；所有旧 ref 作废。

### 关闭详情遮罩

详情遮罩覆盖在结果页之上，遮罩开着时点击背景卡片会打空（`page click` 仍返回 `clicked: true`）。`discover.py` 按两条路依序尝试：

1. `locators.yaml` 的 `detail.close_control`（`button` + `close-icon`）；
2. `detail.dismiss_keys`（默认 `Escape`），发在 `detail.mask` / `detail.container` 上。

窄版布局（实测 viewport 600×740）下小红书把关闭按钮设为 `display:none`，所以第 1 条路不通、实际生效的是 Escape。两条都不通时脚本报错中止，而不是继续点遮罩。

## 脚本入口：何时使用、如何使用

脚本由智能体调用，用户通常只需提出任务，不需要手动填写 ref。它们不替代智能体的页面理解：`ref` 会在页面刷新、打开详情或切换轮播后失效，必须由智能体从**当次** snapshot 重新解析。

| 脚本 | 使用时机 | 输入 | 输出 | 不负责的事 |
|---|---|---|---|---|
| `scripts/discover.py` | 已完成搜索、当前处于结果页时 | `tab-id`、候选数量；`--open-rank` 可顺带打开 | `/search_result/` 候选的 rank、ref、title、noteId、href；打开时返回核验过的 `noteId` 与所用 `mode` | 默认不打开详情；不保证裸 href 可访问 |
| `scripts/collect.py` | 已打开一条详情时 | `tab-id`、选择是否下载图片/视频；ref 可作为回退参数 | 单条笔记 JSON、下载状态、文件名 | 不搜索、不绕过 App-only/验证码/登录 |

### 1. 结果页：发现候选笔记

智能体先在当前搜索结果 tab 运行：

```bash
python playbooks/xiaohongshu/scripts/discover.py --tab-id <search-tab-id> --limit 10
```

候选由 `locators.yaml` 的 `search.result_link` 规则筛选：必须是可见、有尺寸、带 `xsec_token` 的 `/search_result/` 卡片链接。标题优先由同 href 的 title anchor 关联，缺失时才取包含卡片文本。打开第一条的推荐方式：

```bash
python playbooks/xiaohongshu/scripts/discover.py \
  --tab-id <search-tab-id> --limit 10 --open-rank 1
```

若点击被页面改版阻断，才显式改用 `--open-mode navigate`；该模式仍只使用这次 discovery 输出的完整 href。

### 2. 详情页：收集一条笔记

智能体打开详情后，`collect.py` 会从**当次** snapshot 按 `locators.yaml` 解析正文、图片/视频和评论容器。评论未挂载时，它按 `scroll.comments` 的步长滚动 `note-scroller`，直到 `stop_when` 里的规则命中（默认 `moved_false` 或 `no_progress`），再解析已挂载的评论。命令行 ref 仅用于规则暂时失配时的回退。随后运行：

```bash
python playbooks/xiaohongshu/scripts/collect.py \
  --tab-id <detail-tab-id> \
  --images-ref <slider-ref> \
  --download-images \
  --prefix <note-id> \
  --output-dir outputs/xiaohongshu/<note-id>
```

`--comment-scrolls N` 是**最多滚动步数的上限**，不是「滚 N 次」：不传时用 `locators.yaml` 的 `scroll.comments.max_steps`。它应该只在需要主动收紧上限时使用；正常情况下不要传，交给配置决定。

视频笔记将 `--images-ref ... --download-images` 换成 `--media-ref <player-ref> --download-media`。图文和视频都可以保留评论参数。`--output-dir` 会生成统一的笔记目录：`note.json` 放正文、评论和下载记录，图片放 `images/`，视频放 `videos/`。脚本会只下载已发现且符合笔记原图特征的 URL；`downloads` 中必须逐项为 `state=complete` 才算下载成功。

兼容旧用法的 `--output <json-path>` 仍可使用，但媒体会放在该 JSON 同级的 `images/`、`videos/` 目录；新任务应优先使用 `--output-dir`，避免不同笔记的媒体混放。

如页面发生重渲染、脚本提示 ref 不存在、内容为 App-only 或下载候选为空，停止复用旧 ref，回到 snapshot 与页面状态判断步骤；不要让脚本猜测选择器。

## 正文与评论

正文使用 `page text --ref <body-ref>`；评论的定位与滚动由 `collect.py` 读取 `locators.yaml` 后完成，智能体不应再写死评论容器 ref 或滚动距离。

评论仅代表 Web 页面当前滚动/展开后已加载的内容。`note.json` 的 `comments.items` 是 `{author, text}` 记录；时间/地区、点赞、回复按钮、回复展开提示和作者徽标等 UI 元数据不会写入每条评论，完整页面原始文本保留在 `comments.rawText`。需要更多折叠回复时，智能体先点击“展开 N 条回复”，再重新执行采集。

`scroll.comments.stop_when` 支持 `moved_false`（CLI 报告无法继续移动）、`no_progress`（位置与最大滚动量较上一步没变）、`at_max`（已到 `maxScrollY`），按顺序取第一个命中的规则结束循环。达到 `max_steps` 仍未终止时，`note.json` 会带一条「滚动达到上限」的 warning。

## `locators.yaml`：页面规则与脚本边界

`locators.yaml` 是本站 Playbook 的页面语义配置：结果链接路径与访问上下文、卡片标题关联、详情关闭控件与 `dismiss_keys`、正文/媒体/评论容器，以及评论滚动步长/上限/`stop_when` 均在此维护。`discover.py` 和 `collect.py` 只读取配置、在**当次** snapshot 中解析 ref、调用通用 CLI；不得把站点路径、class 关键词或滚动终止规则重新写回脚本。

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
- 遮罩关不掉（`close_control` 不可见且 `dismiss_keys` 无效）：`discover.py` 报错中止，此时应原样重新导航到搜索页 URL，不要带着遮罩继续点卡片；
- `--open-rank` 报「没有落在目标笔记」：说明 click 和 navigate 都没能把页面带到目标，不要沿用当前页面继续采集；
- 评论回复展开和虚拟轮播仍由智能体根据实时 DOM 编排；
- 首页 Top 由网站当次排序决定，不假设固定结果。

## 验证用例

- 关键词：`稻城亚丁攻略`；
- 图文：正文、轮播、评论；视频：direct MP4、正文、评论；
- 失败：App-only、缺失或过期 `xsec_token`。

本次真实探索证据见 `fixtures/exploration-2026-08-20.md`。
