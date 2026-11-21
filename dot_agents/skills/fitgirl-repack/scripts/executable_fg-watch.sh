#!/usr/bin/env bash
# fg-watch.sh — 采样 FitGirl 安装器进度与存活状态
# 用法: fg-watch.sh [间隔秒=15] [安装目录]
# Ctrl-C 退出。
set -uo pipefail

INTERVAL="${1:-15}"
GAME="${2:-$PWD}"
HZ=$(getconf CLK_TCK 2>/dev/null || echo 100)

[ -n "${DISPLAY:-}" ] || export DISPLAY=:0

find_pid() {
  pgrep -x setup.tmp 2>/dev/null | head -1 || pgrep -f 'setup\.tmp' 2>/dev/null | head -1
}

progress_title() {
  local id name
  for id in $(xdotool search --name '%' 2>/dev/null); do
    name=$(xdotool getwindowname "$id" 2>/dev/null) || continue
    case "$name" in
      [0-9]*%*) printf '%s' "$name"; return 0 ;;
    esac
  done
  return 1
}

cpu_ticks() { awk '{print $14+$15}' "/proc/$1/stat" 2>/dev/null || echo 0; }

io_bytes() {
  awk -F'[: ]+' '/^rchar/{r=$2}/^wchar/{w=$2}END{print r+0, w+0}' "/proc/$1/io" 2>/dev/null \
    || echo "0 0"
}

spin_threads() {
  local n=0 t
  for t in /proc/"$1"/task/*; do
    [ "$(cat "$t/wchan" 2>/dev/null)" = "0" ] && n=$((n + 1))
  done
  echo "$n"
}

prev_ticks=""; prev_r=""; prev_w=""; prev_time=""
last_title=""; same=0; hint=0; i=0

while :; do
  P=$(find_pid)
  if [ -z "$P" ]; then
    echo "setup.tmp 未运行（安装已结束、还没开始，或已经崩了）"
    exit 0
  fi

  now=$(date +%s)
  t=$(progress_title || true)
  ticks=$(cpu_ticks "$P")
  read -r r w <<<"$(io_bytes "$P")"
  spin=$(spin_threads "$P")

  cpu="--"; rate="--"
  if [ -n "$prev_time" ] && [ "$now" -gt "$prev_time" ]; then
    dt=$((now - prev_time))
    cpu=$(awk -v a="$prev_ticks" -v b="$ticks" -v hz="$HZ" -v dt="$dt" \
      'BEGIN{printf "%.0f%%", (b-a)/hz/dt*100}')
    rate=$(awk -v r1="$prev_r" -v r2="$r" -v w1="$prev_w" -v w2="$w" -v dt="$dt" \
      'BEGIN{printf "r=%.1f w=%.1f MB/s", (r2-r1)/1048576/dt, (w2-w1)/1048576/dt}')
  fi

  if [ "$t" = "$last_title" ] && [ -n "$t" ]; then
    same=$((same + 1))
  else
    same=0
    last_title="$t"
  fi

  i=$((i + 1))
  size=""
  if [ $((i % 4)) -eq 1 ]; then
    size=$(du -sh "$GAME" 2>/dev/null | cut -f1)
  fi

  flag=""
  [ "$same" -ge 3 ] && flag="STALL(${same}x)"

  printf '%s  %-22s %s  cpu=%-5s %s  spin=%s %s\n' \
    "$(date +%H:%M:%S)" "${t:-<无进度窗口>}" "${size:+size=$size}" "$cpu" "$rate" "$spin" "$flag"

  if [ "$same" -eq 3 ] && [ "$hint" -eq 0 ]; then
    hint=1
    echo "  ↳ 标题 3 次未变。按 references/diagnostics.md 取证：/proc/$P/io、/proc/$P/fd、线程 wchan、dmesg"
  fi

  prev_ticks=$ticks; prev_r=$r; prev_w=$w; prev_time=$now
  sleep "$INTERVAL"
done
