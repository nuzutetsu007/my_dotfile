#!/usr/bin/env bash
# Search anime resources on Mikan Project (蜜柑计划)
# Usage: search_mikan.sh <keyword> [page]
# Output: JSON with title, size, magnet, torrent_url, date

set -euo pipefail

KEYWORD="${1:?Usage: $0 <keyword> [page]}"
PAGE="${2:-1}"
ENCODED_KEYWORD=$(printf '%s' "$KEYWORD" | jq -sRr @uri)

URL="https://mikan.tangbai.cc/Home/Search?searchstr=${ENCODED_KEYWORD}"

TMP_HTML=$(mktemp /tmp/mikan-XXXX.html)
trap 'rm -f "$TMP_HTML"' EXIT

curl -sL "$URL" \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  -o "$TMP_HTML"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/parse_mikan.py" "$TMP_HTML"