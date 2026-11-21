#!/usr/bin/env python3
"""PDF → EPUB with MinerU 4.x (no torch), then structure cleanup + EPUBCheck.

Run with the skill venv:
    ~/.local/share/mineru-skill/venv/bin/python convert.py book.pdf -o book.epub

MinerU's CLI can only emit markdown/json/zip; EPUB is exposed through the Python
renderer, which is why this wrapper exists.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
STRUCTURE = SKILL_ROOT / "scripts" / "structure.py"
DEFAULT_EPUBCHECK = Path(
    os.environ.get("MINERU_SKILL_HOME", Path.home() / ".local/share/mineru-skill")
) / "epubcheck" / "epubcheck.jar"


def guess_language(text: str) -> str:
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    han = len(re.findall(r"[\u4e00-\u9fff]", text))
    if kana > 50:
        return "ja"
    if han > 50:
        return "zh"
    return "und"


def find_epubcheck(explicit: str) -> Path | None:
    for cand in (explicit, os.environ.get("EPUBCHECK_JAR", ""),
                 str(DEFAULT_EPUBCHECK), shutil.which("epubcheck") or ""):
        if not cand:
            continue
        p = Path(cand)
        if p.is_file():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="MinerU PDF → EPUB")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="", help="output .epub (default: next to the PDF)")
    ap.add_argument("--tier", default="basic",
                    choices=["flash", "basic", "standard", "advanced"],
                    help="flash = no model download; basic = 0.8 GB ONNX models")
    ap.add_argument("--ocr-mode", default="txt", choices=["auto", "txt", "ocr"],
                    help="txt = trust the PDF text layer (default)")
    ap.add_argument("--pages", default="all", help="page range, e.g. 1-20,5,r3-r1")
    ap.add_argument("--title", default="")
    ap.add_argument("--language", default="", help="dc:language (auto-guessed if empty)")
    ap.add_argument("--author", action="append", default=[])
    ap.add_argument("--markdown", default="", help="also save markdown here")
    ap.add_argument("--workdir", default="")
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--no-structure", action="store_true",
                    help="keep MinerU's flat headings / single-file EPUB")
    ap.add_argument("--profile", default="auto", choices=["auto", "ja-legal", "generic"])
    ap.add_argument("--keep-toc", action="store_true")
    ap.add_argument("--no-split", action="store_true")
    ap.add_argument("--max-nav-level", type=int, default=3)
    ap.add_argument("--no-epubcheck", action="store_true")
    ap.add_argument("--epubcheck", default="", help="path to epubcheck.jar")
    a = ap.parse_args()

    src = Path(a.pdf).expanduser().resolve()
    if not src.is_file():
        print(f"✘ not found: {src}")
        return 1
    out = Path(a.out).expanduser().resolve() if a.out else src.with_suffix(".epub")

    from mineru.parser import parse
    from mineru.render import EpubRenderOptions, RenderFormat, render

    work = Path(a.workdir).expanduser().resolve() if a.workdir else Path(
        tempfile.mkdtemp(prefix="mineru-"))
    work.mkdir(parents=True, exist_ok=True)
    raw_epub = work / "raw.epub"

    t0 = time.time()
    print(f"[parse] {src.name} tier={a.tier} ocr={a.ocr_mode} pages={a.pages}", flush=True)
    result = parse(str(src), tier=a.tier, ocr_mode=a.ocr_mode,
                   page_range="" if a.pages in ("all", "") else a.pages)
    print(f"[parse] {len(result.pages)} pages in {time.time() - t0:.0f}s", flush=True)

    if a.markdown:
        md_path = Path(a.markdown).expanduser().resolve()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(result.markdown(), encoding="utf-8")
        print(f"[md] {md_path}")

    title = a.title or src.stem
    lang = a.language
    if not lang:
        lang = guess_language(result.markdown()[:20000])
    raw_epub.write_bytes(render(
        result.middle_json, RenderFormat.EPUB,
        options=EpubRenderOptions(title=title, language=lang,
                                  authors=tuple(a.author))))
    print(f"[epub] raw {raw_epub.stat().st_size / 1e6:.1f} MB, language={lang}", flush=True)

    if a.no_structure:
        shutil.copyfile(raw_epub, out)
    else:
        cmd = [sys.executable, str(STRUCTURE), str(raw_epub), "-o", str(out),
               "--profile", a.profile, "--max-nav-level", str(a.max_nav_level)]
        if a.keep_toc:
            cmd.append("--keep-toc")
        if a.no_split:
            cmd.append("--no-split")
        print("[structure] rebuilding headings / nav / chapters", flush=True)
        subprocess.run(cmd, check=True)

    if not a.no_epubcheck:
        jar = find_epubcheck(a.epubcheck)
        if not jar:
            print("[check] epubcheck.jar not found, skipped")
        elif not shutil.which("java"):
            print("[check] java not found, skipped")
        else:
            print("[check] epubcheck", flush=True)
            cp = subprocess.run(["java", "-jar", str(jar), str(out)],
                                capture_output=True, text=True)
            tail = (cp.stdout + cp.stderr).strip().splitlines()[-4:]
            print("\n".join("  " + line for line in tail))
            if cp.returncode != 0:
                print("  ✘ validation failed (EPUB still written)")
                return 2

    if not a.keep_work and not a.workdir:
        shutil.rmtree(work, ignore_errors=True)
    print(f"✔ {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
