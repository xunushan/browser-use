# PRD: Chrome Agent V1 — 本地浏览器自动化系统

## Problem Statement

用户需要一个能够接管现有 Chrome 浏览器的本地自动化系统，由 Codex Skill 驱动。系统需要：

1. 接管用户当前 Chrome Profile 中已有的标签页、登录状态和扩展环境
2. 在 Chrome 关闭时自动启动，Chrome 打开时直接连接
3. 通过 DOM 优先策略完成导航、点击、输入、滚动和内容提取
4. 在 DOM 不足时，按需截取页面区域并调用视觉模型理解
5. 安全地处理登录交接，不绕过验证码和安全策略
6. 对外暴露稳定的 CLI 接口，由 Skill 负责工作流编排

## Solution

构建一个分层架构的本地浏览器自动化系统：

- **Skill 层**：调用 CLI，执行 DOM 优先策略、登录交接、敏感操作确认
- **CLI 层**：无状态薄客户端，将命令转换为本地 RPC
- **Daemon 层**：长期运行的本地服务，管理扩展连接、标签页、任务状态
- **Native Messaging Host**：轻量转发进程，连接扩展和 Daemon
- **Chrome 扩展**：MV3 Service Worker + Content Script，执行 DOM 操作和截图

## User Stories

1. 作为用户，我希望智能体能接管我已登录的小红书账号，搜索"318攻略"，以便获取旅行信息。
2. 作为用户，我希望智能体能登录火山引擎控制台，查看 Coding Plan 使用量，以便了解资源消耗。
3. 作为用户，我希望系统在 Chrome 关闭时自动启动 Chrome，不需要我手动操作。
4. 作为用户，我希望系统在 Chrome 已打开时直接连接，不重启浏览器。
5. 作为用户，我希望登录时由我自己在页面中输入密码和验证码，智能体不接触敏感信息。
6. 作为用户，我希望截图分析前获得明确提示，并知道哪些数据会发送给外部模型。
7. 作为开发者，我希望系统提供稳定的 CLI 接口，方便集成到 Skill 工作流中。
8. 作为开发者，我希望 DOM 操作失败时，系统能建议视觉分析作为备选方案。
9. 作为开发者，我希望元素引用在页面刷新后自动失效，避免操作错误元素。
10. 作为开发者，我希望系统记录操作日志，但不记录敏感输入值和截图内容。
11. 作为用户，我希望任务结束后系统释放标签页控制权，不关闭我的标签页。
12. 作为开发者，我希望系统支持按需注入 Content Script，而不是对所有页面永久注入。
13. 作为用户，我希望系统只请求必要的站点权限，不会自动访问所有网站。
14. 作为开发者，我希望系统支持站点适配器，针对不同网站定制登录检测逻辑。
15. 作为用户，我希望验证码输入使用安全通道，不显示在命令行历史中。

## Implementation Decisions

### 架构决策

- **连接架构**：Skill → CLI → Daemon ↔ Native Host ↔ Chrome 扩展（MV3 Service Worker）
- **通信协议**：JSON-RPC 2.0，Native Messaging 使用 4 字节长度前缀 + UTF-8 JSON
- **扩展连接**：Service Worker 通过 `connectNative()` 建立持久连接，退避重连策略
- **Daemon 启动**：按需自动启动，CLI 和 Native Host 都调用 `ensureDaemon()`

### DOM 与视觉

- **元素引用**：递增 ID，基于 `documentId + frameId + tabId` 隔离，使用 `WeakMap`/`WeakRef`
- **快照粒度**：`viewport`（默认）、`full`、`element`，可配置
- **交互元素**：标准元素 + ARIA role + 高置信度启发式（标注 `source` 和 `confidence`）
- **视觉触发**：Skill 主导，Daemon 返回结构化 `visionSuggestion`，不自动调用
- **截图策略**：元素/区域优先，视口兜底，整页例外

### 安全与登录

- **登录状态**：多状态模型（`AUTHENTICATED`/`UNAUTHENTICATED`/`AUTHENTICATING`/`CHALLENGE_REQUIRED`/`SESSION_EXPIRED`/`UNKNOWN`）
- **人机交接**：优先页面输入，可选安全输入通道（无回显 TTY + Secret Store）
- **敏感数据**：默认脱敏，密码永远页面输入
- **状态缓存**：不持久化，普通操作 15-30s 内存缓存，敏感操作强制重检

### 错误与恢复

- **错误码**：标准 JSON-RPC + 自定义业务码
- **重试**：Daemon 自动重试瞬时错误，Skill 处理业务错误
- **任务状态**：V1 内存状态，崩溃后 Skill 重新发起

## Testing Decisions

### 测试 Seam

**CLI 接口层**作为最高层测试 seam，通过 `chrome-agent` CLI 命令测试端到端流程。

### 测试策略

- **单元测试**：Daemon 内部模块（JSON-RPC 处理、状态机、视觉 provider）
- **集成测试**：CLI → Daemon → Native Host → 扩展 的完整链路
- **端到端测试**：小红书搜索、火山引擎登录两个用例

### 测试原则

- 只测试外部行为，不测试实现细节
- 使用 mock 扩展和 mock 视觉模型进行隔离测试
- 端到端测试需要真实 Chrome 环境

## Out of Scope

- V2 的 Puppeteer/CDP 高级能力
- MCP 适配器
- Windows/Linux 支持（首期仅 macOS）
- 系统服务管理器（`launchd`/`systemd`）
- 多用户并发支持

## Further Notes

- 站点适配器采用插件化设计，方便后续扩展
- 视觉模型 provider 可替换，方便切换不同模型
- 所有外部副作用都需要 `operationId`，支持幂等重试
- 敏感操作（发送验证码、提交登录等）需要用户明确确认
