---
name: mineru-epub
description: Convert a PDF into a clean, validated EPUB with MinerU (no torch, ONNX models). Use whenever the user asks to turn a PDF into EPUB or e-book, 把 PDF 转成 EPUB / 转成电子书, extract a PDF's text+images+tables into reflowable XHTML, fix headings/table of contents in an existing EPUB, or run MinerU locally. Handles text-layer PDFs and scanned PDFs, per-chapter splitting, nested nav, and EPUBCheck validation.
---

# MinerU PDF → EPUB

One command turns a PDF into an EPUB that actually reads like a book: chapters split into separate XHTML files, heading levels inferred from the text, a nested table of contents, images and HTML tables preserved, and EPUBCheck run at the end.

The heavy lifting is MinerU 4.x in `basic` tier: ONNX layout/table/formula models, **no torch**, works on CPU. Everything lives on disk (venv, models, uv cache, epubcheck), so the first run after install is the slow one, not every run.

## Quick start

```bash
S=~/.agents/skills/mineru-epub/scripts

"$S/pdf2epub" book.pdf                       # → book.epub next to the PDF
"$S/pdf2epub" book.pdf -o /tmp/book.epub     # explicit output
"$S/pdf2epub" book.pdf --pages 1-20          # only part of the book (debug / preview)
"$S/pdf2epub" book.pdf --title "題名" --language ja --author "著者"
"$S/pdf2epub" scan.pdf --ocr-mode ocr        # no text layer → OCR
"$S/pdf2epub" book.pdf --markdown book.md    # also keep the markdown
```

`pdf2epub` is a thin launcher for `convert.py` inside the skill venv; you can also call
`~/.local/share/mineru-skill/venv/bin/python "$S/convert.py" ...` directly.

The command prints one line per stage (`[parse]`, `[epub]`, `[structure]`, `[check]`) and ends with `✔ path (MB)`. Exit code `2` means the EPUB was written but EPUBCheck failed — read the reported messages.

## First-time install (only if the venv is missing)

```bash
~/.agents/skills/mineru-epub/scripts/setup.sh            # venv + basic models
~/.agents/skills/mineru-epub/scripts/setup.sh --tier none  # venv only, flash tier usable
```

Needs `uv` on PATH and `java` for EPUBCheck. Downloads ~1.4 GB in total (venv ~600 MB, models ~820 MB). It picks the newest available Python from 3.14 down to 3.10, and installs `pymupdf` alongside MinerU for the table-repair recipe below.

## Tiers

| Tier | Models | When |
|---|---|---|
| `flash` | none | Native text PDF, simple layout, fastest, zero download. Headings come out flat and structure is rough. |
| `basic` | 0.8 GB ONNX (layout, table, formula) | **Default.** Real-world books: multi-column, tables, figures. ~0.3 page/s on CPU. |
| `standard` | ~2 GB, adds llama.cpp VLM | Hard layouts (scans, dense figures). Much slower on CPU. |
| `advanced` | larger VLM | Only with a GPU that can afford it. |

For a 150-page Japanese textbook, `basic` took about 9 minutes. Five pages took 32 seconds including model load, so always smoke-test with `--pages 1-5` before committing to a long run.

## Options that matter

| Option | Meaning |
|---|---|
| `--pages 1-20,35,r3-r1` | MinerU page range; `all` by default. `r` counts from the end. |
| `--ocr-mode txt\|ocr\|auto` | `txt` trusts the PDF text layer (default, fastest, exact characters). Use `ocr` for scans, `auto` to let MinerU decide. |
| `--no-structure` | Keep MinerU's raw EPUB (one big XHTML, flat `<h2>`s) |
| `--profile auto\|ja-legal\|generic` | Heading inference rule set; `auto` picks `ja-legal` when it sees several `第N章/第N節` |
| `--keep-toc` | Keep the printed table of contents parsed as body text (normally dropped as duplicate) |
| `--no-split` | Do not split one file per top-level heading |
| `--max-nav-level N` | Depth of the nested nav (default 3) |
| `--markdown PATH` | Also write MinerU's markdown |
| `--workdir DIR` / `--keep-work` | Keep MinerU's intermediate output for debugging |
| `--epubcheck PATH` | Jar location; also `$EPUBCHECK_JAR` |
| `--no-epubcheck` | Skip validation |

## What the structure pass does

`convert.py` calls `scripts/structure.py` on MinerU's raw EPUB. It is stdlib-only and can be run on any MinerU EPUB:

```bash
python3 "$S/structure.py" raw.epub -o fixed.epub --profile auto
```

1. **Re-levels headings.** MinerU emits every `paragraph_title` as `<h2>` and all text as flat blocks. The script assigns levels with regex rules (`第N章` → h1, `第N節` → h2, `1 ...` → h3, `ア ...` / `（1）...` → h4) and demotes anything that ends in a sentence mark to a paragraph.
2. **Drops the printed TOC.** When a `目次` block is followed by the real body and ≥60 % of the lines look like TOC entries, it is removed (the EPUB nav replaces it).
3. **Splits one XHTML per chapter**, numbered `section-NN.xhtml`, each with its own `<title>` and heading ids.
4. **Rebuilds `nav.xhtml`** as a properly nested `<ol>` from the heading hierarchy, and rewrites the OPF manifest/spine.
5. **Cleanup.** Inline runs inside headings are flattened, `○` bullet prefixes stripped, revision notes (`（...公安告...）`) demoted to `<p class="docvortex-note">`, and small CSS rules appended for the new classes.
6. **MathML.** `properties="mathml"` is added **only** to section files that actually contain MathML. Adding it globally makes EPUBCheck report OPF-015/OPF-014.

## Validation

EPUBCheck 5.2.1 runs automatically at the end:

```bash
java -jar ~/.local/share/mineru-skill/epubcheck/epubcheck.jar book.epub
```

Target output is `0 fatal / 0 error / 0 warning`. Warnings about `dc:language` or remote fonts are usually safe to ignore; errors are not.

## Paths

| What | Where |
|---|---|
| venv | `~/.local/share/mineru-skill/venv` |
| uv cache | `~/.local/share/mineru-skill/uv-cache` |
| EPUBCheck | `~/.local/share/mineru-skill/epubcheck/epubcheck.jar` |
| Models (`MINERU_HOME`) | `~/.mineru` |
| Scripts | `~/.agents/skills/mineru-epub/scripts/` |

Override with `MINERU_SKILL_HOME`, `MINERU_VENV`, `MINERU_HOME`, `UV_CACHE_DIR`.

## Images inside table cells (known defect)

MinerU's table → HTML step is the weak spot for ruled tables where one cell holds **both** a label and a figure (sign charts, 付表, parts lists). Two failure modes, both from MinerU itself — `structure.py` never drops a `<div>`:

1. **Figures dropped.** The table keeps its text columns and contains no `<img>` at all, even though the PDF has pictures in the first column.
2. **Off-by-one placement.** Figures are emitted in their own `<td rowspan="...">` row, so the reader sees the picture one row below the label it belongs to.

Always audit image coverage before delivering a book that has figures:

```bash
# 1. how many image objects does the PDF actually have?
pdfimages -list book.pdf | awk 'NR>2 && $1 ~ /^[0-9]+$/' | wc -l

# 2. how many <img> tags made it into the EPUB? (run in the skill venv)
~/.local/share/mineru-skill/venv/bin/python - <<'EOF' book.epub
import re, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
tags = sum(len(re.findall(r"<img\b", z.read(n).decode()))
           for n in z.namelist() if n.endswith(".xhtml"))
assets = sum(1 for n in z.namelist() if n.endswith((".jpg", ".png", ".gif", ".svg")))
print(f"img tags={tags} assets={assets}")
EOF

# 3. table inventory: rows, image count, first labels — spot the picture-less one
python3 - <<'EOF' book.epub
import io, sys, zipfile
from xml.etree import ElementTree as ET
X = "{http://www.w3.org/1999/xhtml}"
z = zipfile.ZipFile(sys.argv[1])
for n in z.namelist():
    if not n.endswith(".xhtml"):
        continue
    root = ET.parse(io.BytesIO(z.read(n))).getroot()
    for ti, table in enumerate(root.iter(X + "table"), 1):
        rows = [tr for tr in table.iter(X + "tr") if tr.find(X + "td") is not None]
        labels = ["".join(r.find(X + "td").itertext()).strip() for r in rows]
        labels = [x for x in labels if x][:3]
        imgs = len(list(table.iter(X + "img")))
        print(f"{n} table{ti}: rows={len(rows)} imgs={imgs} | " + " / ".join(labels))
EOF
```

A gap between 1 and 2 means figures were lost. Snippet 3 shows where: a table whose first column is sign/plate names but reports `imgs=0` is exactly the broken case (one PDF table is often split into several HTML tables, so several consecutive entries may all read `imgs=0`). Report it in the delivery instead of shipping silently — the text is intact, only the pictures are affected.

### Repairing such tables from PDF geometry

Ruled tables can be rebuilt exactly. `pymupdf` is installed in the skill venv for this:

```python
import pymupdf
page = pymupdf.open("book.pdf")[110]          # 0-based page

# grid: table borders are thin filled rects, not stroked lines
hs = [d["rect"] for d in page.get_drawings() if d["rect"].height < 2 and d["rect"].width > 3]
vs = [d["rect"] for d in page.get_drawings() if d["rect"].width < 2 and d["rect"].height > 3]
rows = sorted({round(r.y0, 1) for r in hs})   # horizontal boundaries
cols = sorted({round(r.x0, 1) for r in vs})   # column boundaries

# per row: label = words in the first column; figure = drawings/images below it
words = page.get_text("words")
for top, bot in zip(rows, rows[1:]):
    cell = [w for w in words if top < (w[1] + w[3]) / 2 < bot and cols[0] < w[0] < cols[1]]
    if not cell:
        continue
    label_bottom = max(w[3] for w in cell)
    figs = [d["rect"] for d in page.get_drawings()
            if top < d["rect"].y0 and d["rect"].y1 < bot
            and cols[0] < d["rect"].x0 and d["rect"].x1 < cols[1]
            and d["rect"].y0 > label_bottom - 2 and d["rect"].height > 2]
    figs += [r for r in (page.get_image_bbox(i) for i in page.get_images(full=True))
             if r and top < r.y0 and r.y1 < bot and cols[0] < r.x0 and r.x1 < cols[1]]
    print(label, min(f.y0 for f in figs), max(f.y1 for f in figs))
```

Crop each `figs` union at 300 dpi (`page.get_pixmap(clip=rect, dpi=300)`) and insert it into the matching `<td>`. Verify the row count of the EPUB table against the PDF rows first; if they differ, fall back to inserting missing figures only.

**Case record** — `交通規則.pdf` (148 pages, 付表3 = sign charts on pages 95–143): PDF has 277 image objects, the EPUB had 253. The 24 missing figures were the whole `ウ 補助標識` table (pages 109–112); additionally `エ 案内標識` rows 101+ and 規制標識 rows 徐行 / 歩行者等横断禁止 had their pictures shifted one row down. Everything else (229 figures) was correctly placed.

## Pitfalls

- **Scripts that call MinerU need `if __name__ == "__main__":`.** MinerU spawns worker processes; without the guard you get `ConnectionResetError` / `EOFError` from the spawn.
- Models must go to a persistent `MINERU_HOME` (`~/.mineru`). If it points into `/tmp`, every reboot re-downloads 820 MB.
- Model source in mainland China: `MINERU_MODEL_SOURCE=modelscope <venv>/bin/mineru-kit models download --tier basic`. Add `--help` to `mineru-kit models` for other sources.
- `mineru-kit models verify --tier basic` is the fast health check after moving models.
- **Do not use `--tier flash` for real books.** It skips models entirely and the layout is unusable (no headings, no tables).
- A PDF whose text layer is broken stays broken: missing dakuten, `っ` extracted as `つ`, `しよう` split as `しよ う`. Compare with `pdftotext` before blaming MinerU — the source file is usually at fault. Do not "fix" it blindly.
- EPUB from MinerU is only available through the Python renderer (`mineru.render.render(..., RenderFormat.EPUB)`); the CLI emits markdown/JSON/zip only. That is why `convert.py` exists.
- `EpubRenderOptions(authors=...)` needs a tuple, not a string.
- Long books: run in the background and check the stage lines rather than blocking the conversation. Parsing is ~0.3 page/s.
- Figures inside table cells are the one thing MinerU gets wrong often enough to audit every time — see “Images inside table cells” above.

## Rules

- Never invent chapter structure. If `--profile auto` guesses wrong, look at the actual headings and use `generic` or adjust the regexes.
- Report the final path, file size, page/section/nav counts, and the EPUBCheck verdict.
- Keep working files in `/tmp` and clean them up; only the venv, models, and epubcheck belong on disk.
