#!/usr/bin/env bash
# Install MinerU 4.x for this skill: venv + models, no torch.
set -euo pipefail

ROOT="${MINERU_SKILL_HOME:-$HOME/.local/share/mineru-skill}"
VENV="${MINERU_VENV:-$ROOT/venv}"
export MINERU_HOME="${MINERU_HOME:-$HOME/.mineru}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/uv-cache}"
TIER="basic"
PYTHON="${PYTHON:-}"
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --no-models) TIER="none"; shift ;;
    -h|--help)
      cat <<'EOF'
usage: setup.sh [--tier flash|basic|standard|none] [--python 3.12] [--force]

  --tier basic     0.8 GB ONNX models: layout + table + formula (default)
  --tier standard  2 GB ONNX + llama.cpp VLM (slower on CPU, better on hard layouts)
  --tier none      no models: only flash tier works (native text PDFs)
  --python X.Y     interpreter for the venv (default: first of 3.14..3.10)
  --force          recreate the venv even if it already exists
EOF
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }

if [ -z "$PYTHON" ]; then
  for v in 3.14 3.13 3.12 3.11 3.10; do
    if uv python find "$v" >/dev/null 2>&1; then PYTHON="$v"; break; fi
  done
fi
PYTHON="${PYTHON:-3.12}"

mkdir -p "$ROOT" "$MINERU_HOME"
if [ "$FORCE" = 1 ] || [ ! -x "$VENV/bin/python" ]; then
  echo "[venv] $VENV (python $PYTHON)"
  [ "$FORCE" = 1 ] && rm -rf "$VENV"
  uv venv --python "$PYTHON" "$VENV"
  uv pip install --python "$VENV/bin/python" "mineru>=4.0,<5" pymupdf
else
  echo "[venv] already present: $VENV"
fi

if [ "$TIER" != "none" ]; then
  echo "[models] tier=$TIER → $MINERU_HOME"
  MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-modelscope}" \
    "$VENV/bin/mineru-kit" models download --tier "$TIER"
  "$VENV/bin/mineru-kit" models verify --tier "$TIER"
fi

du -sh "$VENV" "$MINERU_HOME" 2>/dev/null || true
cat <<EOF

done. usage:
  $ROOT/scripts/pdf2epub  book.pdf -o book.epub
  $ROOT/venv/bin/python $ROOT/scripts/convert.py book.pdf --tier flash -o book.epub
EOF
