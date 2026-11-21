#!/usr/bin/env bash
# fg-install.sh — 用 umu + GE-Proton 静默安装 FitGirl repack
# 用法: fg-install.sh <repack目录> <安装目录> [unit名]
set -euo pipefail

die() { printf '错误: %s\n' "$*" >&2; exit 1; }

[ $# -ge 2 ] || die "用法: $0 <repack目录> <安装目录> [unit名]"

REPACK=$(cd "$1" && pwd) || die "repack 目录不存在: $1"
INSTALL="$2"
UNIT="${3:-fg-install}"

[ -f "$REPACK/setup.exe" ] || die "$REPACK 下没有 setup.exe"
command -v umu-run >/dev/null || die "找不到 umu-run"
command -v systemd-run >/dev/null || die "找不到 systemd-run"

mkdir -p "$INSTALL"
INSTALL=$(cd "$INSTALL" && pwd)

# 防止重复起同名 unit
if systemctl --user is-active --quiet "$UNIT" 2>/dev/null; then
  die "unit $UNIT 已在运行；先 systemctl --user status $UNIT 或换一个名字"
fi

SLUG=$(basename "$INSTALL" | tr -cd '[:alnum:]_-')
[ -n "$SLUG" ] || SLUG=fitgirl
PREFIX="${WINEPREFIX:-$HOME/Games/umu/$SLUG}"

if [ -z "${PROTONPATH:-}" ]; then
  PROTONPATH=$(ls -d "$HOME/.local/share/Steam/compatibilitytools.d/"*Proton* 2>/dev/null \
    | sort -V | tail -1)
fi
[ -n "${PROTONPATH:-}" ] || die "没有可用的 PROTONPATH（先跑一次 umu-run 让它下载 UMU-Proton）"

# btrfs 上关掉 CoW/压缩（只影响此后新建的文件）
FSTYPE=$(stat -f -c %T "$INSTALL" 2>/dev/null || echo unknown)
if [ "$FSTYPE" = "btrfs" ] && command -v chattr >/dev/null 2>&1; then
  chattr +C "$INSTALL" 2>/dev/null && echo "已对 $INSTALL 设置 chattr +C（btrfs 免 CoW）" || true
fi

# Inno 需要 Wine 的 Z: 盘路径，且反斜杠
to_win() { printf 'Z:%s' "$1" | tr '/' '\\'; }
WIN_DIR=$(to_win "$INSTALL")
WIN_LOG=$(to_win "$REPACK/install-inno.log")

echo "repack : $REPACK"
echo "install: $INSTALL"
echo "prefix : $PREFIX"
echo "proton : $PROTONPATH"
echo "unit   : $UNIT"
echo

systemd-run --user --unit="$UNIT" --collect \
  --working-directory="$REPACK" \
  --property=TimeoutStopSec=60 \
  --setenv=HOME="$HOME" \
  --setenv=DISPLAY="${DISPLAY:-:0}" \
  --setenv=WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
  --setenv=XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
  --setenv=GAMEID="${GAMEID:-umu-default}" \
  --setenv=WINEPREFIX="$PREFIX" \
  --setenv=PROTONPATH="$PROTONPATH" \
  --setenv=__GLX_VENDOR_LIBRARY_NAME="${__GLX_VENDOR_LIBRARY_NAME:-mesa}" \
  "$(command -v umu-run)" ./setup.exe \
    /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /CLOSEAPPLICATIONS \
    "/DIR=$WIN_DIR" "/LOG=$WIN_LOG"

cat <<EOF

已启动。跟进命令：
  systemctl --user status $UNIT
  journalctl --user -u $UNIT -f
  bash "$(dirname "$0")/fg-watch.sh" 15 "$INSTALL"

注意：install-inno.log 里的 "Installation process succeeded" 只代表 Inno 外壳阶段，
解压还要几十分钟。真正的完成信号是进度标题消失 + 目录体积稳定 + md5 全通过。
EOF
