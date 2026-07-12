# Chrome Agent

Chrome Agent 是一个本地浏览器自动化系统，由 Codex Skill 驱动，能够接管用户现有的 Chrome 浏览器。

## 架构

```
Skill → CLI → Daemon ↔ Native Host ↔ Chrome 扩展
```

- **Skill 层**：调用 CLI，执行 DOM 优先策略
- **CLI 层**：无状态薄客户端
- **Daemon 层**：长期运行的本地服务
- **Native Messaging Host**：轻量转发进程
- **Chrome 扩展**：MV3 Service Worker + Content Script

## 安装

```bash
pip install -e .
```

## 使用

```bash
# 确保 daemon 运行
chrome-agent ensure --launch-if-missing

# 查看状态
chrome-agent status

# 启动 daemon
chrome-agent start

# 停止 daemon
chrome-agent stop

# 查看版本
chrome-agent version
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码格式化
ruff check .
ruff format .

# 类型检查
mypy chrome_agent
```

## 许可证

MIT
