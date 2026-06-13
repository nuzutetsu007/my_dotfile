#!/usr/bin/env bash
# Search anime resources on Nyaa.si
# Usage: search_nyaa.sh <keyword> [page]
# Output: JSON with title, size, seeders, leechers, magnet, detail_url

set -euo pipefail

KEYWORD="${1:?Usage: $0 <keyword> [page]}"
PAGE="${2:-1}"
ENCODED_KEYWORD=$(printf '%s' "$KEYWORD" | jq -sRr @uri)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

URL="https://nyaa.si/?q=${ENCODED_KEYWORD}&f=0&c=1_0&p=${PAGE}"

TMP_HTML=$(mktemp /tmp/nyaa-XXXX.html)
trap 'rm -f "$TMP_HTML"' EXIT

curl -sL "$URL" \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  -o "$TMP_HTML"

python3 "$SCRIPT_DIR/parse_nyaa.py" "$TMP_HTML"