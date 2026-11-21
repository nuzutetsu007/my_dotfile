#!/usr/bin/env bash
# umu 体检报告：runner / 环境变量 / prefix 一览
# 用法: bash umu-report.sh
set -u

C=$'\e[36m'; R=$'\e[0m'
h() { printf '\n%s== %s ==%s\n' "$C" "$1" "$R"; }

h "1) PROTONPATH 解析"
PP="${PROTONPATH:-<未设>}"
echo "当前值: $PP"
CTD="$HOME/.local/share/Steam/compatibilitytools.d"
if [[ -d $CTD ]]; then
  shopt -s nullglob
  for d in "$CTD"/*/; do
    [[ "$(basename "$d")" == LegacyRuntime ]] && { echo "  [运行时组件] $(basename "$d") (非runner)"; continue; }
    printf '  [已装] %s (%s)\n' "$(basename "$d")" "$(du -sh "$d" 2>/dev/null | cut -f1)"
  done
else
  echo "  $CTD 不存在"
fi
# 模拟 umu codename 解析（自然排序取最新）
if [[ "$PP" != /* && "$PP" != "<未设>" ]]; then
  latest=$(ls -1d "$CTD"/"$PP"* 2>/dev/null | sort -V | tail -1)
  [[ -n "$latest" ]] && echo "codename '$PP' 将解析到: $(basename "$latest")"
fi

h "2) 环境变量（三层）"
echo "-- fish 通用变量 --"
grep 'SETUVAR' "$HOME/.config/fish/fish_variables" 2>/dev/null \
  | grep -iE 'proton|wine|umu|gameid' \
  | sed 's/SETUVAR /  /; s/:/ = /; s/\\x2e/./g; s/\\x20/ /g; s/\\x2d/-/g' || echo "  (无)"
echo "-- systemd 用户环境 --"
systemctl --user show-environment 2>/dev/null | grep -iE 'PROTON|WINE|UMU|GAMEID' || echo "  (无)"
echo "-- 当前进程 --"
env | grep -iE '^(PROTON|WINE|UMU|GAMEID)' || echo "  (无)"

h "3) Steam 官方 Proton (steamapps/common)"
for d in "$HOME/.local/share/Steam/steamapps/common/"*[Rr]oton*/; do
  [[ -d "$d" ]] || continue
  v=$(awk '{print $2}' "$d/version" 2>/dev/null)
  printf '  %-40s %s  [version: %s]\n' "$(basename "$d")" "$(du -sh "$d" 2>/dev/null | cut -f1)" "${v:-缺失!}"
done

h "4) 其他 runner (Bottles/Lutris/Heroic)"
for base in "$HOME/.local/share/bottles/runners" "$HOME/.local/share/lutris/runners" "$HOME/.config/heroic/tools"; do
  [[ -d "$base" ]] && find "$base" -mindepth 1 -maxdepth 2 -type d \
    | sed "s|$HOME|~|" | sed 's/^/  /'
done
[[ -d $HOME/.local/share/bottles ]] && { echo "  Bottles 数据目录整体: $(du -sh "$HOME/.local/share/bottles" 2>/dev/null | cut -f1)"; }

h "5) umu prefix 清单 ($HOME/Games/umu)"
for d in "$HOME/Games/umu"/*/; do
  [[ -d "$d" ]] || continue
  ver=$(tr -d '\0' < "$d/version" 2>/dev/null)
  created=$(stat -c '%y' "$d" 2>/dev/null | cut -d' ' -f1)
  cfg=$(grep -oE '(GE-Proton|UMU-Proton)[^ ]*' "$d/config_info" 2>/dev/null | head -1)
  printf '  %-16s 版本:%-12s 创建:%s  建于:%s\n' "$(basename "$d")" "${ver:-?}" "${cfg:-?}" "$created"
done
[[ -d $HOME/Games/umu ]] || echo "  (不存在)"

h "6) 系统包"
pacman -Qq 2>/dev/null | grep -iE 'umu|wine|proton' | sed 's/^/  /'
command -v wine >/dev/null && echo "  系统 wine: $(wine --version 2>/dev/null)" || echo "  无独立系统 wine"