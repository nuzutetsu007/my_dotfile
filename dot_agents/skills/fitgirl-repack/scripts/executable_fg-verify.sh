#!/usr/bin/env bash
# fg-verify.sh — 用 game/_Redist/fitgirl.md5 全量校验安装结果
# 用法: fg-verify.sh <安装目录>
set -uo pipefail

[ $# -ge 1 ] || { echo "用法: $0 <安装目录>" >&2; exit 2; }
GAME=$(cd "$1" 2>/dev/null && pwd) || { echo "目录不存在: $1" >&2; exit 2; }

MD5=$(find "$GAME" -maxdepth 3 -iname 'fitgirl.md5' -print -quit 2>/dev/null)
[ -n "$MD5" ] || { echo "找不到 fitgirl.md5（通常在 _Redist/ 下）" >&2; exit 2; }
BASE=$(dirname "$MD5")

TMP=$(mktemp) || exit 1
OUT=$(mktemp) || exit 1
trap 'rm -f "$TMP" "$OUT"' EXIT

# 清单是 CRLF + 反斜杠 + "..\" 相对路径，基准目录是 _Redist/
tr -d '\r' < "$MD5" | sed 's#\\#/#g' > "$TMP"
TOTAL=$(grep -c '[^[:space:]]' "$TMP")

echo "清单 : $MD5"
echo "基准 : $BASE"
echo "文件 : $TOTAL"
echo

start=$(date +%s)
( cd "$BASE" && LC_ALL=C md5sum -c --quiet "$TMP" ) >"$OUT" 2>&1
rc=$?
elapsed=$(( $(date +%s) - start ))

FAILED=$(grep -cE ': FAILED( open or read)?$' "$OUT" 2>/dev/null || true)
FAILED=${FAILED:-0}

echo "耗时 : ${elapsed}s"
echo "通过 : $((TOTAL - FAILED)) / $TOTAL"

if [ "$rc" -eq 0 ] && [ "$FAILED" -eq 0 ]; then
  echo "结果 : 全部通过 ✓"
  exit 0
fi

echo "结果 : $FAILED 个文件失败 ✗"
[ "$FAILED" -eq 0 ] && echo "       （md5sum 返回 $rc：可能是清单格式/读取错误）"
head -30 "$OUT"
exit 1
