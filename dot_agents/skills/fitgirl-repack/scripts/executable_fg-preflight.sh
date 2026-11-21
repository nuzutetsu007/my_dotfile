#!/usr/bin/env bash
# fg-preflight.sh — FitGirl repack 安装前体检
# 用法: fg-preflight.sh [安装目标目录]
set -uo pipefail

TARGET="${1:-$PWD}"
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m⚠\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }

echo "=== 系统 ==="
printf '  %s\n' "$(uname -srm)"
[ -r /etc/os-release ] && . /etc/os-release && printf '  %s %s\n' "${NAME:-}" "${VERSION_ID:-}"

echo
echo "=== 内存 / swap（解压峰值可达 9~10GB） ==="
awk '/MemTotal|MemAvailable|SwapTotal|SwapFree/{printf "  %-12s %6.1f GiB\n",$1,$2/1048576}' /proc/meminfo
if [ "$(awk '/SwapTotal/{print $2}' /proc/meminfo)" -eq 0 ]; then
  bad "没有 swap：大分卷解压可能被 OOM kill（建议 16G swapfile）"
else
  ok "swap 已启用"
  swapon --show --noheadings 2>/dev/null | sed 's/^/    /'
fi

echo
echo "=== 目标盘 ==="
if [ -d "$TARGET" ]; then
  df -h --output=source,size,used,avail,pcent "$TARGET" | sed 's/^/  /'
  FSTYPE=$(stat -f -c %T "$TARGET" 2>/dev/null)
  OPTS=$(findmnt -no OPTIONS --target "$TARGET" 2>/dev/null)
  printf '  fs=%s\n' "${FSTYPE:-unknown}"
  case "$OPTS" in
    *compress=*)
      warn "启用了透明压缩：$OPTS"
      warn "  66GB 顺序写会明显放大 CPU/延迟；安装目录可先 chattr +C（只对新文件生效）" ;;
    *) ok "无透明压缩" ;;
  esac
else
  bad "目录不存在: $TARGET"
fi

echo
echo "=== CPU 电源 / 频率（最容易忽视的 3 倍差距） ==="
if command -v powerprofilesctl >/dev/null 2>&1; then
  PROFILE=$(powerprofilesctl get 2>/dev/null)
  printf '  power profile: %s\n' "$PROFILE"
  case "$PROFILE" in
    power-saver) bad "power-saver 会把频率钉在 ~1.3GHz，解压慢 3 倍以上；建议 set balanced/performance" ;;
    *) ok "档位正常" ;;
  esac
else
  warn "没有 powerprofilesctl（非 GNOME/未装 power-profiles-daemon）"
fi
printf '  governor: %s\n' "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/a)"
MAXF=0
for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq; do
  [ -r "$f" ] || continue
  v=$(cat "$f" 2>/dev/null || echo 0)
  [ "$v" -gt "$MAXF" ] && MAXF=$v
done
[ "$MAXF" -gt 0 ] && printf '  当前最高频率: %s MHz\n' "$((MAXF / 1000))"

echo
echo "=== umu / Proton ==="
if command -v umu-run >/dev/null 2>&1; then
  ok "umu-run: $(command -v umu-run)"
  timeout 20 umu-run --version 2>&1 | grep -m1 -i 'umu-launcher' | sed 's/^/    /'
else
  bad "找不到 umu-run（安装 umu-launcher 或用 Steam 的 Proton）"
fi
RUNNERS=$(ls -d "$HOME/.local/share/Steam/compatibilitytools.d/"*Proton* 2>/dev/null)
if [ -n "$RUNNERS" ]; then
  printf '  runners:\n'
  printf '%s\n' "$RUNNERS" | sed 's/^/    /'
else
  warn "compatibilitytools.d 下没有 Proton runner（首次运行 umu 会自动下载 UMU-Proton）"
fi
printf '  PROTONPATH(env)=%s\n' "${PROTONPATH:-<未设>}"

echo
echo "=== 图形（Wine 窗口能不能出来） ==="
printf '  DISPLAY=%s WAYLAND_DISPLAY=%s\n' "${DISPLAY:-<未设>}" "${WAYLAND_DISPLAY:-<未设>}"
printf '  __GLX_VENDOR_LIBRARY_NAME=%s\n' "${__GLX_VENDOR_LIBRARY_NAME:-<未设>}"
if command -v glxinfo >/dev/null 2>&1; then
  if glxinfo -B >/dev/null 2>&1; then
    ok "glxinfo 正常"
  else
    warn "glxinfo 失败：Xwayland+NVIDIA 常见 GLX BadValue，运行时加 __GLX_VENDOR_LIBRARY_NAME=mesa"
  fi
else
  warn "未安装 glxinfo（mesa-utils），跳过 GLX 探测"
fi
if [ -n "${WAYLAND_DISPLAY:-}" ] && [ "${__GLX_VENDOR_LIBRARY_NAME:-}" = "nvidia" ]; then
  warn "Xwayland + nvidia GLX：Wine 建窗可能报 X_GLXCreateContext BadValue；建议安装/启动时用 mesa"
fi

echo
echo "=== repack 源目录 ==="
REPACK="${REPACK_DIR:-}"
if [ -n "$REPACK" ] && [ -d "$REPACK" ]; then
  [ -f "$REPACK/setup.exe" ] && ok "setup.exe 存在" || bad "缺少 setup.exe"
  show_bins() {
    find "$REPACK" -maxdepth 1 -name "$1" -printf '%f\t%s\n' 2>/dev/null \
      | sort | while IFS=$'\t' read -r name bytes; do
          printf '    %-44s %s\n' "$name" "$(numfmt --to=iec "$bytes" 2>/dev/null || echo "$bytes")"
        done
  }
  echo "  分卷:"
  show_bins 'fg-[0-9]*.bin'
  echo "  可选分卷（半截的会导致安装器死循环，务必核对大小）:"
  show_bins 'fg-optional-*.bin'
  [ -f "$REPACK/MD5/fitgirl-bins.md5" ] && ok "有 MD5/fitgirl-bins.md5（可校验分卷）" || warn "没有分卷 md5 清单"
else
  printf '  （用 REPACK_DIR=<repack目录> 再跑一次可检查 setup.exe / 分卷完整性）\n'
fi

echo
echo "体检结束。红线项先处理，再开安装。"
