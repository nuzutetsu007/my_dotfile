#!/usr/bin/env bash
# 审计所有 agent 的 skill 目录：重名、失效软链、空目录、公共目录外的散落副本
# 用法: bash audit.sh [--quiet]
set -u

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

SHARED="$HOME/.agents/skills"

# 用户级目录: 标签|路径
USER_DIRS="
shared|$HOME/.agents/skills
opencode|$HOME/.config/opencode/skills
pi|$HOME/.pi/agent/skills
claude-code|$HOME/.claude/skills
codex|$HOME/.codex/skills
gemini-cli|$HOME/.gemini/skills
"

# 项目级目录: 从 cwd 向上找，以及显式列出的常见仓库
PROJ_DIRS=""
d="$PWD"
for _ in 1 2 3; do
  for sub in .agents/skills .opencode/skills .opencode/skill .claude/skills .codex/skills; do
    [ -d "$d/$sub" ] && PROJ_DIRS="$PROJ_DIRS
项目($d)|$d/$sub"
  done
  d="$(dirname "$d")"
done

say() { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }

printf '=== 已安装的 skill ===\n'
printf '%-22s %-8s %-10s %s\n' NAME SCOPE TYPE PATH
FOUND_NAMES=""
PROBLEMS=0

scan() { # $1=label $2=dir
  local label="$1" dir="$2" e name type
  [ -d "$dir" ] || return 0
  for e in "$dir"/*; do
    name="$(basename "$e")"
    if [ -L "$e" ]; then
      # 坏链要单独报，-e 对它为假，不能靠 -d 过滤
      if [ -e "$e" ]; then type="symlink"; else type="BROKEN"; PROBLEMS=$((PROBLEMS+1)); fi
    elif [ -d "$e" ]; then
      type="dir"
    else
      continue
    fi
    [ -f "$e/SKILL.md" ] || { [ "$type" = BROKEN ] || continue; }
    printf '%-22s %-8s %-10s %s\n' "$name" "$label" "$type" "$e" | sed "s|$HOME|~|"
    [ "$type" = BROKEN ] && continue
    FOUND_NAMES="$FOUND_NAMES
$name|$label"
  done
}

while IFS='|' read -r label dir; do
  [ -n "${label:-}" ] && scan "$label" "$dir"
done <<EOF
$(printf '%s\n%s' "$USER_DIRS" "$PROJ_DIRS")
EOF

printf '\n=== 重名检查 ===\n'
DUP=0
for n in $(printf '%s\n' "$FOUND_NAMES" | sed '/^$/d' | cut -d'|' -f1 | sort -u); do
  hits="$(printf '%s\n' "$FOUND_NAMES" | sed '/^$/d' | grep -c "^$n|")"
  if [ "$hits" -gt 1 ]; then
    DUP=1
    printf '  %s 出现 %s 次:\n' "$n" "$hits"
    printf '%s\n' "$FOUND_NAMES" | sed '/^$/d' | grep "^$n|" | sed 's/^/    /'
  fi
done
[ "$DUP" = 0 ] && printf '  无重复\n'

printf '\n=== 公共目录之外的散落副本 ===\n'
STRAY=0
while IFS='|' read -r label dir; do
  [ -z "${label:-}" ] && continue
  case "$dir" in "$SHARED") continue ;; esac
  [ -d "$dir" ] || continue
  for e in "$dir"/*/; do
    [ -f "$e/SKILL.md" ] || continue
    n="$(basename "$e")"
    STRAY=1
    printf '  %s 在 %s 也有一份（应搬去 ~/.agents/skills）\n' "$n" "$label"
  done
done <<EOF
$(printf '%s\n%s' "$USER_DIRS" "$PROJ_DIRS")
EOF
[ "$STRAY" = 0 ] && printf '  无\n'

printf '\n=== 空目录 ===\n'
EMPTY=0
while IFS='|' read -r label dir; do
  [ -z "${label:-}" ] && continue
  case "$dir" in "$SHARED") continue ;; esac
  if [ -d "$dir" ] && [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
    EMPTY=1; printf '  %s (%s) 为空\n' "$dir" "$label" | sed "s|$HOME|~|"
  fi
done <<EOF
$(printf '%s\n%s' "$USER_DIRS" "$PROJ_DIRS")
EOF
[ "$EMPTY" = 0 ] && printf '  无\n'

printf '\n=== 汇总 ===\n'
printf '  公共目录 skill 数: %s\n' "$(ls -d "$SHARED"/*/ 2>/dev/null | wc -l)"
if [ "$DUP" = 0 ] && [ "$STRAY" = 0 ] && [ "$PROBLEMS" = 0 ]; then
  printf '  状态: 干净\n'
else
  printf '  状态: 有 %s 类问题待处理（重名=%s 散落=%s 坏链=%s）\n' \
    "$(( (DUP>0) + (STRAY>0) + (PROBLEMS>0) ))" "$DUP" "$STRAY" "$PROBLEMS"
fi
