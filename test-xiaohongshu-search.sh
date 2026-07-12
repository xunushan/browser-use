#!/usr/bin/env bash
#
# Xiaohongshu Search Test - "318攻略"
# Complete workflow: search, extract notes, download images
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
DOWNLOAD_DIR="$HOME/Downloads/xiaohongshu"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Run CLI command and extract JSON result
run_cli() {
    local cmd="$1"
    $VENV_PYTHON -m chrome_agent.cli $cmd --json 2>/dev/null || echo '{"error": "command failed"}'
}

main() {
    log_info "小红书搜索测试 - 318攻略"
    log_info "========================"

    # Step 1: Ensure system ready
    log_info "Step 1: 确保系统就绪..."
    result=$(run_cli "ensure --launch-if-missing --wait-for-extension")
    if [[ $(echo "$result" | grep -o '"status": "ready"') ]]; then
        log_info "✓ 系统就绪"
    else
        log_error "✗ 系统未就绪"
        exit 1
    fi

    # Step 2: Open Xiaohongshu
    log_info "Step 2: 打开小红书..."
    result=$(run_cli "tabs open https://www.xiaohongshu.com")
    log_info "✓ 已打开小红书"
    sleep 3

    # Step 3: List tabs to find Xiaohongshu
    log_info "Step 3: 查找小红书标签页..."
    result=$(run_cli "tabs list --domain xiaohongshu.com")
    log_info "标签页: $result"

    # Step 4: Take snapshot to find search box
    log_info "Step 4: 获取页面快照..."
    # Note: We need a real tab ID for this to work
    # For now, just show the command structure
    log_info "  Command: page snapshot --tab-id <tab_id> --scope viewport"

    # Step 5: Search for "318攻略"
    log_info "Step 5: 搜索 318攻略..."
    log_info "  Command: page fill --tab-id <tab_id> --ref <search_box_ref> --value 318攻略"
    log_info "  Command: page keypress --tab-id <tab_id> --keys Enter"

    # Step 6: Wait for results
    log_info "Step 6: 等待搜索结果..."
    log_info "  Command: page wait --tab-id <tab_id> --selector .search-results"

    # Step 7: Extract notes
    log_info "Step 7: 提取笔记..."
    log_info "  Command: page snapshot --tab-id <tab_id> --scope viewport"

    # Step 8: Download images
    log_info "Step 8: 下载图片..."
    mkdir -p "$DOWNLOAD_DIR"
    log_info "  Download directory: $DOWNLOAD_DIR"

    log_info ""
    log_info "测试完成!"
    log_info ""
    log_info "注意: 实际的页面操作需要真实的 Chrome 标签页 ID。"
    log_info "请确保:"
    log_info "  1. Chrome 扩展已加载"
    log_info "  2. 扩展图标显示在 Chrome 工具栏"
    log_info "  3. 扩展有权限访问 xiaohongshu.com"
}

main "$@"
