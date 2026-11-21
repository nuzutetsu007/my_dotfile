#!/usr/bin/env python3
"""Restructure a MinerU 4.x EPUB: heading levels, nested nav, one file per chapter.

MinerU renders every `paragraph_title` as a flat <h2> and puts the whole book in
one content.xhtml. This script re-levels headings, drops a duplicated printed
table of contents, splits by top-level headings, and rebuilds nav.xhtml.

Only the Python standard library is required, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

XHTML = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
MATH = "http://www.w3.org/1998/Math/MathML"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"

for prefix, uri in (("", XHTML), ("epub", EPUB_NS), ("math", MATH)):
    ET.register_namespace(prefix, uri)

X = f"{{{XHTML}}}"

JA_CHAP = re.compile(r"^第\d+章\s*\S")
JA_SEC = re.compile(r"^第\d+節\s*\S")
JA_NUM = re.compile(r"^\d+\s+\S")
JA_SUB = re.compile(r"^（\d+）\s*\S{1,30}$")
JA_APPENDIX = re.compile(r"^付表\d+")
JA_SUPP = re.compile(r"^附\s*則")
JA_LETTER = re.compile(r"^[アイウエオ]\s+\S")
JA_NOTE = re.compile(r"^（[^）]*公安告[^）]*）$")
TOC_ENTRY = re.compile(r"^(第\d+[章節]|付表|附\s*則|\d+\s)")
SENTENCE_END = ("。", "．", ".", "！", "？", "!", "?")


def block_text(el: ET.Element) -> str:
    return "".join(el.itertext()).strip()


def classify(text: str, profile: str, source_tag: str, doc_title: str) -> tuple[int, str]:
    """Return (level, kind); kind is heading | note | title | body."""
    if profile == "ja-legal":
        if text.startswith("○") and len(text) < 40:
            return 1, "title"
        if text == doc_title:
            return 0, "title"
        if JA_CHAP.match(text) and len(text) <= 60:
            return 1, "heading"
        if JA_SUPP.match(text) or JA_APPENDIX.match(text):
            return 1, "heading"
        if JA_SEC.match(text) and len(text) <= 60:
            return 2, "heading"
        probe = re.sub(r"（[^）]*）", "", text)
        if JA_NUM.match(text) and not probe.rstrip().endswith(SENTENCE_END) and len(text) <= 60:
            return 3, "heading"
        if JA_LETTER.match(text) and len(text) <= 40:
            return 4, "heading"
        if JA_SUB.match(text) and not text.endswith(SENTENCE_END):
            return 4, "heading"
        if JA_NOTE.match(text):
            return 0, "note"
        if source_tag == "h2" and len(text) <= 60 and not text.endswith(SENTENCE_END):
            return 2, "heading"
        return 0, "body"

    if source_tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return int(source_tag[1]), "heading"
    return 0, "body"


def set_tag(el: ET.Element, tag: str, attrs: dict) -> None:
    el.tag = f"{X}{tag}"
    el.attrib.clear()
    el.attrib.update(attrs)


def drop_printed_toc(divs: list[ET.Element]) -> list[ET.Element]:
    """Remove the parsed paper TOC when it is followed by the real body."""
    start = next((i for i, d in enumerate(divs) if block_text(d) == "目次"), None)
    if start is None:
        return divs
    body = None
    for i in range(start + 1, len(divs)):
        d = divs[i]
        t = block_text(d)
        if d.get("data-block-type") == "paragraph_title" and re.match(r"^第\d+章\s", t):
            body = i
            break
    if body is None:
        return divs
    region = divs[start:body]
    if not 5 <= len(region) <= 300:
        return divs
    toc_like = sum(1 for d in region if TOC_ENTRY.match(block_text(d)))
    if toc_like / len(region) < 0.6:
        return divs
    print(f"  drop printed TOC: {len(region)} blocks (pages "
          f"{region[0].get('data-page-idx', '?')}-{region[-1].get('data-page-idx', '?')})")
    return divs[:start] + divs[body:]


def build(src: Path, out: Path, profile_arg: str, keep_toc: bool,
          split: bool, max_level: int) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="epub-fix-"))
    try:
        with zipfile.ZipFile(src) as zf:
            zf.extractall(tmp)
        container = ET.parse(tmp / "META-INF/container.xml").getroot()
        rootfile = container.find(f".//{{{CONTAINER}}}rootfile")
        if rootfile is None:
            rootfile = container.find(".//rootfile")
        if rootfile is None:
            raise SystemExit("container.xml has no rootfile")
        opf_rel = rootfile.get("full-path")
        opf_path = tmp / opf_rel
        opf_root = ET.parse(opf_path).getroot()
        manifest = opf_root.find(f"{{{OPF}}}manifest")
        spine = opf_root.find(f"{{{OPF}}}spine")
        items = {it.get("id"): it for it in manifest}
        nav_id = next((it.get("id") for it in manifest
                       if it.get("properties") and "nav" in it.get("properties").split()), None)
        spine_ids = [ref.get("idref") for ref in spine]
        content_ids = [i for i in spine_ids if i != nav_id]
        if len(content_ids) != 1:
            raise SystemExit(f"expected a single content document, found {len(content_ids)}")
        content_href = items[content_ids[0]].get("href")
        content_path = (opf_path.parent / content_href).resolve()
        doc_title = (opf_root.findtext(f".//{{{DC}}}title") or content_path.stem).strip()
        lang = (opf_root.findtext(f".//{{{DC}}}language") or "und").strip() or "und"

        root = ET.parse(content_path).getroot()
        article = root.find(f".//{X}article")
        if article is None:
            article = root.find(f".//{X}body")
        if article is None:
            raise SystemExit("content document has no article/body")
        divs = list(article)

        texts = [block_text(d) for d in divs]
        ja_hits = sum(1 for t in texts if re.match(r"^第\d+[章節]\s", t))
        profile = profile_arg
        if profile == "auto":
            profile = "ja-legal" if ja_hits >= 3 else "generic"
        print(f"  profile: {profile}")

        if profile == "ja-legal" and not keep_toc:
            divs = drop_printed_toc(divs)

        first_seen = False
        for div in divs:
            if len(div) != 1:
                continue
            child = div[0]
            tag = child.tag.split("}")[1]
            if tag not in ("p", "h1", "h2", "h3", "h4", "h5", "h6"):
                continue
            text = block_text(div)
            if not text:
                continue
            level, kind = classify(text, profile, tag, doc_title)
            if kind == "note":
                set_tag(child, "p", {"class": "docvortex-note"})
                continue
            if kind == "title":
                if level == 0 and first_seen:
                    set_tag(child, "p", {"class": "docvortex-title"})
                    continue
                level, kind = level or 1, "heading"
            first_seen = True
            if kind != "heading":
                if tag.startswith("h"):
                    set_tag(child, "p", {"class": "docvortex-text"})
                continue
            if text.startswith("○") and level == 1:
                text = text[1:].strip()
            set_tag(child, "h", {"class": f"docvortex-heading docvortex-heading--{level}"})
            child.tag = f"{X}h{level}"
            for sub in list(child):
                child.remove(sub)
            child.text = text

        section_files: list[str] = []
        if split:
            sections: list[list[ET.Element]] = []
            for div in divs:
                is_h1 = len(div) == 1 and div[0].tag == f"{X}h1"
                if is_h1 or not sections:
                    sections.append([])
                sections[-1].append(div)
        else:
            sections = [divs]
        if not sections:
            raise SystemExit("no content blocks found")

        text_dir = content_path.parent
        stale = {p.name for p in text_dir.glob("section-*.xhtml")}
        opf_dir = opf_path.parent

        html_head = "<?xml version='1.0' encoding='utf-8'?>\n<!DOCTYPE html>\n"
        nav_entries: list[tuple[int, str, str]] = []
        new_items: list[tuple[str, str, bool]] = []
        for idx, blocks in enumerate(sections, start=1):
            fname = f"section-{idx:02d}.xhtml"
            html = ET.Element(f"{X}html", {"lang": lang, "xml:lang": lang})
            head = ET.SubElement(html, f"{X}head")
            ET.SubElement(head, f"{X}meta", {"charset": "utf-8"})
            title = next((block_text(b) for b in blocks
                          if len(b) == 1 and b[0].tag == f"{X}h1"), doc_title)
            ET.SubElement(head, f"{X}title").text = title
            ET.SubElement(head, f"{X}link",
                          {"rel": "stylesheet", "href": "../styles/docvortex.css",
                           "type": "text/css"})
            body = ET.SubElement(html, f"{X}body", {"class": "docvortex-epub-body"})
            art = ET.SubElement(body, f"{X}article", {"class": "docvortex-document"})
            if idx == 1:
                art.set("id", "content-start")
            hcount = 0
            for div in blocks:
                art.append(div)
                if len(div) != 1:
                    continue
                m = re.fullmatch(r"h([1-6])", div[0].tag.split("}")[1])
                if not m:
                    continue
                level = int(m.group(1))
                hcount += 1
                hid = f"h{idx}-{hcount}"
                div[0].attrib["id"] = hid
                if level <= max_level:
                    nav_entries.append((level, block_text(div), f"{fname}#{hid}"))
            xml = ET.tostring(html, encoding="unicode")
            (text_dir / fname).write_text(html_head + xml + "\n", encoding="utf-8")
            math_in_section = any(
                any(e.tag.startswith(f"{{{MATH}}}") for e in b.iter()) for b in blocks)
            new_items.append((fname, fname, math_in_section))
            section_files.append(fname)

        if not nav_entries:
            nav_entries = [(2, doc_title, f"{section_files[0]}#content-start")]

        # remove the old content doc
        content_path.unlink(missing_ok=True)
        for name in stale - set(section_files):
            (text_dir / name).unlink(missing_ok=True)

        # nav
        nav_path = (opf_dir / items[nav_id].get("href")).resolve()
        rel_prefix = os.path.relpath(text_dir, nav_path.parent).replace(os.sep, "/")
        nav = ET.Element(f"{X}html", {"lang": lang, "xml:lang": lang})
        nhead = ET.SubElement(nav, f"{X}head")
        ET.SubElement(nhead, f"{X}meta", {"charset": "utf-8"})
        ET.SubElement(nhead, f"{X}title").text = "目次"
        ET.SubElement(nhead, f"{X}link",
                      {"rel": "stylesheet", "href": "styles/docvortex.css",
                       "type": "text/css"})
        nbody = ET.SubElement(nav, f"{X}body")
        nav_el = ET.SubElement(nbody, f"{X}nav",
                               {"id": "toc", "role": "doc-toc", f"{{{EPUB_NS}}}type": "toc"})
        ET.SubElement(nav_el, f"{X}h1").text = "目次"
        root_ol = ET.SubElement(nav_el, f"{X}ol")
        stack = [(0, root_ol)]
        for level, text, href in nav_entries:
            while stack and stack[-1][0] >= level:
                stack.pop()
            li = ET.SubElement(stack[-1][1], f"{X}li")
            ET.SubElement(li, f"{X}a", {"href": f"{rel_prefix}/{href}"}).text = text
            if level < max_level:
                stack.append((level, ET.SubElement(li, f"{X}ol")))
        for parent in list(nav_el.iter()):
            for child in list(parent):
                if child.tag == f"{X}ol" and len(child) == 0:
                    parent.remove(child)
        nav_path.write_text(html_head + ET.tostring(nav, encoding="unicode") + "\n",
                            encoding="utf-8")

        # opf
        for item in list(manifest):
            if item.get("id") in content_ids:
                manifest.remove(item)
        for ref in list(spine):
            spine.remove(ref)
        for idx, (fname, _, math) in enumerate(new_items, start=1):
            attrs = {"id": f"sec{idx}", "href": f"text/{fname}",
                     "media-type": "application/xhtml+xml"}
            if math:
                attrs["properties"] = "mathml"
            ET.SubElement(manifest, f"{{{OPF}}}item", attrs)
            ET.SubElement(spine, f"{{{OPF}}}itemref", {"idref": f"sec{idx}"})

        ET.register_namespace("", OPF)
        ET.register_namespace("dc", DC)
        opf_path.write_text("<?xml version='1.0' encoding='utf-8'?>\n"
                            + ET.tostring(opf_root, encoding="unicode"), encoding="utf-8")

        css = opf_dir / "styles/docvortex.css"
        if css.exists():
            extra = css.read_text(encoding="utf-8")
            if ".docvortex-note" not in extra:
                extra += """

.docvortex-note {
  font-size: 0.82em;
  color: #57606a;
  margin: 0.3em 0 0.9em;
}

h1.docvortex-heading { font-size: 1.6em; margin: 1.6em 0 0.7em; }
h2.docvortex-heading { font-size: 1.28em; margin: 1.4em 0 0.6em; }
h3.docvortex-heading { font-size: 1.08em; margin: 1.2em 0 0.5em; }
h4.docvortex-heading { font-size: 1em; margin: 1em 0 0.4em; }

.docvortex-title {
  font-weight: bold;
  text-align: center;
  margin: 1.4em 0;
}
"""
                css.write_text(extra, encoding="utf-8")

        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                        compress_type=zipfile.ZIP_STORED)
            for path in sorted(tmp.rglob("*")):
                if path.is_file() and path.name != "mimetype":
                    zf.write(path, str(path.relative_to(tmp)), zipfile.ZIP_DEFLATED)
        print(f"  wrote {len(sections)} section files, {len(nav_entries)} nav entries")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Restructure a MinerU EPUB")
    ap.add_argument("epub")
    ap.add_argument("-o", "--out", default="", help="output path (default: <input>.fixed.epub)")
    ap.add_argument("--profile", choices=("auto", "ja-legal", "generic"), default="auto")
    ap.add_argument("--keep-toc", action="store_true", help="keep the parsed printed TOC")
    ap.add_argument("--no-split", action="store_true", help="keep one content file")
    ap.add_argument("--max-nav-level", type=int, default=3)
    a = ap.parse_args()
    src = Path(a.epub)
    out = Path(a.out) if a.out else src.with_suffix(".fixed.epub")
    build(src, out, a.profile, a.keep_toc, not a.no_split, a.max_nav_level)
    print(f"✔ {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
