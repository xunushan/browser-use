# 网站探索与站点 Skill 规范

## 目标

把跨网站能力保留在 Chrome Agent CLI，把网站结构、状态、恢复规则和确定性解析代码放进
**该站点自己的 skill**。站点 skill 是独立项目空间，不在本 skill 目录里：它只通过
`chrome-agent` 的命令面驱动浏览器，不 import 本 skill 的代码、不依赖本目录的路径
（契约见 `SKILL.md` 第 4 节）。探索时只使用用户授权的当前 Chrome，不绕过登录、验证码、
扫码、风控或内容保护。

## 新网站探索流程

1. `ensure → tabs list/claim → full snapshot` 建立页面基线。
2. 探索搜索、结果、详情打开方式及完整 href；禁止删除 token、签名、来源和过期参数。
3. 识别最窄的标题、正文、媒体、评论容器以及背景/推荐排除区域。
4. 验证实际滚动容器、懒加载、虚拟化列表、展开回复和媒体资源形态。
5. 覆盖未登录、验证码、App-only、访问限制、ref 过期、URL 过期和下载失败。
6. 用可观察状态验证每一步；命令返回不等于业务完成。
7. 记录关键观测与失败证据（放进该站点的 PLAYBOOK），不保存 Cookie、密码、OTP 或真实短期 token。

## 工具分工

- `page snapshot`：定位和布局，不用于最终长正文。
- `page text --ref`：正文和已加载评论。
- `page images/download-images --ref`：目标媒体容器中的图片。
- `page media/download-media --ref`：视频/音频发现及 direct 资源下载。
- `page scroll --ref`：内部容器懒加载。
- `page validate/click/wait`：动态控件和状态转换。

媒体容器的 `<video>` 可能是 `blob:`，而可下载地址存在于页面级 JSON-LD。探索时比较 scoped 与
page-level media，按当前详情状态、类型、时长和结构化数据关联，不能只检查播放器子树。

## 站点 skill 的包结构

```text
<站点 skill 目录>/     # 独立项目空间；整个目录就是技能目录
  SKILL.md             # 入口：`description` 决定什么时候被选中，正文指向 PLAYBOOK
  PLAYBOOK.md          # 流程 / 踩坑与证据 / 目录与文件职责
  locators.yaml        # 页面语义规则（选择器、作用域、阈值）
  scripts/             # 确定性编排：CLI 调用、解析、去重、格式化、落盘
  schemas/             # 产出文件的结构合同，与脚本产出逐字段对应
  tests/               # 规则单测 + 产出与合同一致性
```

站点脚本在自己的目录树内互相引用，用绝对路径运行；**不要写死本机 skill 路径，也不要去探测
`chrome-agent` 的安装位置**——命令名就是接口，PATH 上的 `chrome-agent` 就是它。

## PLAYBOOK 必备章节

三节，缺一不可：

```markdown
# <网站>内容采集 Playbook
适用站点：`example.com`（包括其子域名）

## 1 完整流程        # 照顺序跑完即一次采集；每步一条可直接粘贴的命令 + 判据
## 2 关键踩坑与证据   # 一条结论一行，附观测或实测证据；出问题回来查
## 3 目录与文件职责   # 各文件是什么、谁读它、什么时候改
```

它是行为准则，不是日志：不写"这次改了什么"的变迁史，不写"验证用例"清单（回归测试在
`tests/` 里），也不重复同一事实三遍。

## 语义规则

优先级：role/name/label/可见文字 → 标签和 href 模式/容器关系 → 稳定业务属性 → class 关键词弱提示 → 视觉坐标兜底。不得写死 tab ID、ref、签名 URL、token 或一次运行的动态 class。

## 页面状态模型

显式定义状态、转换和可观察判据，例如：

```text
SEARCH → RESULT_READY → DETAIL_OPEN
DETAIL_OPEN → BODY_READY → MEDIA_READY → COMMENTS_READY
任意状态 → LOGIN_HANDOFF / ACCESS_DENIED / REF_STALE
```

## 代码与智能体边界

智能体负责首次探索、语义判断、实时 ref 解析、异常决策和 Playbook 更新。脚本负责固定命令序列、JSON 解析、URL 去重、下载状态汇总、Schema 校验和文件输出。脚本不得用硬编码 selector 绕开实时 ref，也不得自行处理登录/风控。

## 完成条件

- 来源完整 URL 保留；
- 正文未静默截断；
- 评论标记加载范围；
- 图片/视频属于目标容器；
- 下载返回 `state=complete` 和 filename；
- blob/HLS/DASH/DRM 等能力缺口明确报告；
- 输出满足 Schema；
- 高风险状态正确交给用户。
