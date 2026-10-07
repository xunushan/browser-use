# Chrome Agent 后续迭代路线

## 1. 当前基线

当前 V1 已具备：现有 Chrome 登录态复用、标签页管理、完整链接保留、DOM snapshot/ref、点击/填写/按键、内部容器滚动、等待、结构化提取、按 ref 获取长正文、图片发现与下载、direct 视频/音频发现与下载、Skill 编排及站点权限边界。

## 2. P0：稳定当前内容下载闭环

- 为 `page text/images/media` 增加统一 scope、document ID 校验和结构化错误码；
- 图片与媒体下载支持显式 URL 白名单选择，避免只依赖 `limit`；
- 下载任务持久化、取消、进度查询和断点恢复；
- 增加文件 MIME、大小、hash 和扩展名校验；
- 修复 screenshot：校验活动 tab，避免截错后台标签页；
- 为站点 skill 提供可选的产出 schema 校验与回归位（站点侧实现，本仓库只提供接口）；
- 增加 modal、虚拟轮播、懒加载和短期签名 URL 的端到端测试。

## 3. P1：CDP/Puppeteer 高级浏览器能力

- 通过用户批准的 `chrome.debugger` 附加指定 tab；
- iframe、复杂 Shadow DOM、浏览器弹窗和可靠等待；
- Network/Response、Console、下载事件与页面生命周期；
- `Page.captureScreenshot` 和元素裁剪；
- 保持 DOM 原语为默认，仅在需要时升级 CDP。

## 4. P1：流媒体能力

- `blob:` 与 MediaSource 诊断；
- HLS `.m3u8`、DASH `.mpd` 清单发现；
- 音视频轨道和分片元数据展示；
- 在平台条款和用户授权允许时下载分片、校验并合并；
- DRM/加密内容明确不支持，不绕过内容保护；
- signed URL 过期检测和重新发现。

## 5. P1：站点 Skill 系统

- 站点 skill 与本仓库之间只有命令面契约：为它加版本校验，让不兼容在调用时报错而不是静默走偏；
- 语义规则、页面状态机、完成条件和恢复规则；
- 探索轨迹脱敏后生成候选 Playbook；
- Playbook 回放、差异检测和改版告警；
- 网站知识不进入 CLI，跨网站能力经评审后下沉。

## 6. P2：多模态视觉

- daemon 内增加可替换 VisionProvider；
- 视口、元素和区域截图及 DPR/zoom/scroll 元数据；
- DOM/A11y 优先，局部视觉 grounding 兜底；
- 视觉候选绑定回 DOM ref 后再执行；
- 纯坐标动作的区域约束、置信度阈值和人工确认；
- 动作前后截图/DOM diff 验证；
- 截图裁剪、脱敏、保留策略和提示注入检测；
- 对照通用 VLM、Computer Use API 与本地 UI-TARS 类模型。

## 7. P2：可靠性与安全

- 任务级 tab claim、会话租约和并发隔离；
- 操作审计不记录输入秘密和原始截图；
- 下载、上传、发布、删除、支付的分级确认策略；
- 页面提示注入与数据外传防护；
- 扩展/daemon 协议版本协商；
- Native Host 重连和 daemon 启动竞态修复；
- 可观察性：步骤耗时、重试原因、ref 失效率、下载成功率。

## 8. P3：桌面与手机 Executor

- DesktopExecutor：macOS Accessibility 或 Windows UIA + screenshot；
- AndroidExecutor：ADB/UIAutomator2/Appium + screenshot；
- 统一 observation/action/result schema；
- 每台设备独立授权、会话和安全边界；
- 用 OSWorld、AndroidWorld 子集和自有真实任务评测；
- iOS/XCTest 在 Android PoC 稳定后评估。

## 9. 验收指标

- 内容任务成功率和字段完整率；
- 正文截断漏报率为 0；
- 目标媒体准确率，背景资源误下载率；
- 轮播完整率与重复率；
- direct/stream/blob 分类准确率；
- 每任务模型调用、截图数量、耗时和下载失败率；
- 网站改版后的恢复成功率；
- 高风险动作未经确认执行次数为 0。
