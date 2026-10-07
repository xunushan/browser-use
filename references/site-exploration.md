# 新网站探索

拿到一个没碰过的网站，用本工具把它摸清楚。这里只讲**怎么探索**；一个站点的采集流程、状态、
恢复规则和确定性解析代码写到**该站点自己的 skill** 里，它的文件该怎么组织不归本文件管。

探索时只使用用户授权的当前 Chrome，不绕过登录、验证码、扫码、风控或内容保护。

## 探索流程

1. `ensure → tabs list/claim → full snapshot` 建立页面基线。扩展不预置任何站点权限，先
   `chrome-agent sites list --json` 看目标站点是否已授权；未授权时命令会返回
   `Site access not granted for <host>`，让用户在该标签页点扩展图标授权后重试。授权一次即
   长期有效，但站点 skill 里要写上这一步，别当成故障。
2. 探索搜索、结果、详情打开方式及完整 href；禁止删除 token、签名、来源和过期参数。
3. 识别最窄的标题、正文、媒体、评论容器以及背景/推荐排除区域。
4. 验证实际滚动容器、懒加载、虚拟化列表、展开回复和媒体资源形态。
5. 覆盖未登录、验证码、App-only、访问限制、ref 过期、URL 过期和下载失败。
6. 用可观察状态验证每一步；命令返回不等于业务完成。
7. 记录关键观测与失败证据，不保存 Cookie、密码、OTP 或真实短期 token。

## 工具分工

- `page snapshot`：定位和布局，不用于最终长正文。
- `page text --ref`：正文和已加载评论。
- `page images/download-images --ref`：目标媒体容器中的图片。
- `page media/download-media --ref`：视频/音频发现及 direct 资源下载。
- `page scroll --ref`：内部容器懒加载。
- `page validate/click/wait`：动态控件和状态转换。

媒体容器的 `<video>` 可能是 `blob:`，而可下载地址存在于页面级 JSON-LD。探索时比较 scoped 与
page-level media，按当前详情状态、类型、时长和结构化数据关联，不能只检查播放器子树。

## 语义规则

优先级：role/name/label/可见文字 → 标签和 href 模式/容器关系 → 稳定业务属性 → class 关键词弱提示 → 视觉坐标兜底。不得写死 tab ID、ref、签名 URL、token 或一次运行的动态 class。

## 页面状态模型

为站点显式定义状态、转换和可观察判据，例如：

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
