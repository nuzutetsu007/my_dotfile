#!/usr/bin/env bash
# rqbit 自维护脚本 — 检测/下载/更新到最新版本
# Usage: install_rqbit.sh [--check] [--force] [--path ~/.local/bin]
#
# 策略:
#   1. GitHub releases/latest 重定向获取最新 tag
#   2. 下载对应 rqbit-linux-amd64
#   3. 验证版本
#   4. 最新版失败 → 回退 v8.1.1

set -euo pipefail

# --- 配置 ---
FALLBACK_VERSION="v8.1.1"
FALLBACK_URL="https://github.com/ikatson/rqbit/releases/download/${FALLBACK_VERSION}/rqbit-linux-amd64"
RELEASES_URL="https://github.com/ikatson/rqbit/releases"
DOWNLOAD_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/rqbit-install"
BINARY_NAME="rqbit-linux-amd64"

# --- 参数 ---
CHECK_ONLY=false
FORCE=false
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) CHECK_ONLY=true; shift ;;
        --force) FORCE=true; shift ;;
        --path) TARGET_DIR="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--check] [--force] [--path DIR]"
            echo "  --check    仅检查版本，不下"
            echo "  --force    强制重下覆盖"
            echo "  --path     安装目录 (默认自动选)"
            exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# --- 检测当前版本 ---
CURRENT_VER=""
CURRENT_PATH=""
if command -v rqbit &>/dev/null; then
    CURRENT_PATH=$(command -v rqbit)
    CURRENT_VER=$(rqbit --version 2>/dev/null || echo "unknown")
elif [[ -x "$HOME/.local/bin/rqbit" ]]; then
    CURRENT_PATH="$HOME/.local/bin/rqbit"
    CURRENT_VER=$("$CURRENT_PATH" --version 2>/dev/null || echo "unknown")
fi

# --- 选择安装目标 ---
if [[ -z "$TARGET_DIR" ]]; then
    if [[ -w "/usr/local/bin" ]]; then
        TARGET_DIR="/usr/local/bin"
    else
        TARGET_DIR="$HOME/.local/bin"
    fi
fi

if $CHECK_ONLY; then
    if [[ -n "$CURRENT_VER" ]]; then
        echo "rqbit $CURRENT_VER @ $CURRENT_PATH"
    else
        echo "rqbit 未安装"
    fi
    exit 0
fi

echo "=== rqbit 版本维护 ==="

# --- 获取最新版本 tag (通过 GitHub redirect) ---
echo -n "▶ 检查最新版本... "
LATEST_TAG=""
LATEST_URL=""

# 方法1: 用 curl -I 跟踪重定向拿 tag
REDIRECT_URL=$(curl -sI -o /dev/null -w '%{redirect_url}' \
    "${RELEASES_URL}/latest" 2>/dev/null || true)

if [[ -n "$REDIRECT_URL" ]]; then
    LATEST_TAG=$(echo "$REDIRECT_URL" | grep -oP 'tag/\K(v?\d+\.\d+\.\d+[-\w.]*)' || true)
fi

# 方法2: 如果方法1失败，直接查已知最新
if [[ -z "$LATEST_TAG" ]]; then
    # 尝试从 releases page 提取
    LATEST_TAG=$(curl -sL -H "User-Agent: Mozilla/5.0" \
        "${RELEASES_URL}" 2>/dev/null \
        | grep -oP '/releases/tag/\K(v?\d+\.\d+\.\d+[^"]*)' \
        | head -1 || true)
fi

if [[ -n "$LATEST_TAG" ]]; then
    LATEST_URL="https://github.com/ikatson/rqbit/releases/download/${LATEST_TAG}/${BINARY_NAME}"
    echo "$LATEST_TAG"
else
    echo "⚠ 无法获取最新版，将回退 $FALLBACK_VERSION"
    LATEST_TAG="$FALLBACK_VERSION"
    LATEST_URL="$FALLBACK_URL"
fi

# --- 版本比较，决定是否需要下载 ---
NEED_DOWNLOAD=false
if [[ -z "$CURRENT_VER" ]]; then
    echo "  → rqbit 未安装"
    NEED_DOWNLOAD=true
elif $FORCE; then
    echo "  → --force 强制更新"
    NEED_DOWNLOAD=true
else
    # 简单比较: 如果当前版本含 tag 中的版本号，且不是 force，跳过
    if echo "$CURRENT_VER" | grep -qi "${LATEST_TAG#v}"; then
        echo "  → 已是最新 ($CURRENT_VER @ $CURRENT_PATH)"
    else
        echo "  → 当前 $CURRENT_VER → 目标 $LATEST_TAG"
        NEED_DOWNLOAD=true
    fi
fi

if ! $NEED_DOWNLOAD; then
    echo "✓ 无需操作"
    exit 0
fi

# --- 下载 ---
mkdir -p "$DOWNLOAD_DIR"
TMP_FILE="$DOWNLOAD_DIR/$BINARY_NAME"

echo -n "▶ 下载 $LATEST_TAG ... "
if curl -sL --connect-timeout 10 --max-time 60 \
    -H "User-Agent: Mozilla/5.0" \
    -o "$TMP_FILE" \
    "$LATEST_URL"; then

    chmod +x "$TMP_FILE"

    # 验证是可执行文件且打印版本
    VER_CHECK=$("$TMP_FILE" --version 2>/dev/null || true)
    if [[ -n "$VER_CHECK" ]]; then
        echo "$VER_CHECK"
        echo "  → 下载成功, 大小 $(du -h "$TMP_FILE" | cut -f1)"
    else
        echo "⚠ 下载文件不可执行"
        rm -f "$TMP_FILE"
        # 如果不是 fallback 而且有 fallback URL，回退
        if [[ "$LATEST_URL" != "$FALLBACK_URL" ]]; then
            echo "  → 回退到 $FALLBACK_VERSION ..."
            LATEST_TAG="$FALLBACK_VERSION"
            LATEST_URL="$FALLBACK_URL"
            if curl -sL --connect-timeout 10 --max-time 60 \
                -o "$TMP_FILE" "$LATEST_URL"; then
                chmod +x "$TMP_FILE"
                VER_CHECK=$("$TMP_FILE" --version 2>/dev/null || true)
                if [[ -z "$VER_CHECK" ]]; then
                    echo "✗ 回退也失败"
                    rm -f "$TMP_FILE"
                    exit 1
                fi
                echo "  → 回退成功: $VER_CHECK"
            fi
        else
            echo "✗ 下载失败"
            rm -f "$TMP_FILE"
            exit 1
        fi
    fi
else
    echo "✗ 网络失败"
    # 如果不是 fallback，尝试回退
    if [[ "$LATEST_URL" != "$FALLBACK_URL" ]]; then
        echo "  → 回退到 $FALLBACK_VERSION ..."
        LATEST_TAG="$FALLBACK_VERSION"
        LATEST_URL="$FALLBACK_URL"
        if curl -sL --connect-timeout 10 --max-time 60 \
            -o "$TMP_FILE" "$LATEST_URL"; then
            chmod +x "$TMP_FILE"
            VER_CHECK=$("$TMP_FILE" --version 2>/dev/null || echo "unknown")
            echo "  → 回退成功: $VER_CHECK"
        else
            echo "✗ 回退也失败"
            rm -f "$TMP_FILE"
            exit 1
        fi
    else
        rm -f "$TMP_FILE"
        exit 1
    fi
fi

# --- 安装 ---
mkdir -p "$TARGET_DIR"
INSTALL_PATH="$TARGET_DIR/rqbit"

echo -n "▶ 安装到 $INSTALL_PATH ... "
cp "$TMP_FILE" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"
echo "完成"

# --- 验证 ---
echo -n "▶ 验证... "
INSTALLED_VER=$("$INSTALL_PATH" --version 2>/dev/null || echo "失败")
if [[ "$INSTALLED_VER" != "失败" ]]; then
    echo "$INSTALLED_VER"
    echo "✓ rqbit 就绪"
else
    echo "✗ 验证失败"
    exit 1
fi

# --- 更新 reference 文件 ---
REF_FILE="$(cd "$(dirname "$0")" && pwd)/../references/rqbit.md"
if [[ -f "$REF_FILE" ]]; then
    # 更新文档中的版本号
    sed -i "s/v[0-9]\+\.[0-9]\+\.[0-9]\+\(-beta\.[0-9]\+\)*/${LATEST_TAG}/g" "$REF_FILE" 2>/dev/null || true
    echo "  → 已更新 $REF_FILE"
fi