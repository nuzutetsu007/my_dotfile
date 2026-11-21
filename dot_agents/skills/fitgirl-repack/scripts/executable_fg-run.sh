#!/usr/bin/env bash
# fg-run.sh — 用 umu + GE-Proton 启动装好的游戏
# 用法: fg-run.sh <游戏目录> [exe] [传给游戏的参数...]
set -euo pipefail

die() { printf '错误: %s\n' "$*" >&2; exit 1; }

[ $# -ge 1 ] || die "用法: $0 <游戏目录> [exe] [参数...]"
GAME=$(cd "$1" 2>/dev/null && pwd) || die "目录不存在: $1"

EXE="${2:-}"
if [ -z "$EXE" ]; then
  # 根目录下体积最大的 exe，排除卸载器
  EXE=$(find "$GAME" -maxdepth 1 -iname '*.exe' ! -iname 'unins*' -printf '%s\t%p\n' 2>/dev/null \
    | sort -rn | head -1 | cut -f2-)
fi
[ -n "$EXE" ] || die "$GAME 根目录下找不到 exe，请显式指定"

SLUG=$(basename "$GAME" | tr -cd '[:alnum:]_-')
[ -n "$SLUG" ] || SLUG=fitgirl
PREFIX="${WINEPREFIX:-$HOME/Games/umu/$SLUG}"

if [ -z "${PROTONPATH:-}" ]; then
  PROTONPATH=$(ls -d "$HOME/.local/share/Steam/compatibilitytools.d/"*Proton* 2>/dev/null \
    | sort -V | tail -1)
fi
[ -n "${PROTONPATH:-}" ] || die "没有可用的 PROTONPATH"

command -v umu-run >/dev/null || die "找不到 umu-run"

printf 'game  : %s\n' "$GAME"
printf 'exe   : %s\n' "$EXE"
printf 'prefix: %s\n' "$PREFIX"
printf 'proton: %s\n\n' "$PROTONPATH"

cd "$GAME"
exec env \
  GAMEID="${GAMEID:-umu-default}" \
  WINEPREFIX="$PREFIX" \
  PROTONPATH="$PROTONPATH" \
  __GLX_VENDOR_LIBRARY_NAME="${__GLX_VENDOR_LIBRARY_NAME:-mesa}" \
  umu-run "$EXE" "${@:3}"
