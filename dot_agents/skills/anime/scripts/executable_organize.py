#!/usr/bin/env python3
"""
Organize downloaded anime files into standard library structure.
Usage: organize.py <source_dir> <anime_name> <season> <bangumi_json>

Renames files according to: {AnimeName} - S{season}E{ep} - {title}.ext
Creates .meta/ directory with source info.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path


EPISODE_PATTERNS = [
    re.compile(r'[Ee][Pp]?\s*(\d+)'),
    re.compile(r'第\s*(\d+)\s*[話话集]'),
    re.compile(r'\b(\d{2})\b'),  # last resort: two-digit numbers
]


def extract_episode(filename: str) -> int | None:
    """Extract episode number from filename."""
    for pattern in EPISODE_PATTERNS:
        m = pattern.search(filename)
        if m:
            ep = int(m.group(1))
            if 1 <= ep <= 999:
                return ep
    return None


def detect_is_special(filename: str) -> bool:
    """Check if file is a special/OVA/extra."""
    return bool(re.search(r'\b(SP|OVA|OAD|Special|NCED|NCOP|Menu|PV|CM|Trailer)\b',
                          filename, re.IGNORECASE))


def get_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    video_exts = {'.mkv', '.mp4', '.avi', '.mov', '.ts', '.webm', '.m2ts'}
    return ext if ext in video_exts else ''


def organize(source_dir: str, anime_name: str, season: int, bangumi_data: dict):
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"Source directory not found: {source_dir}")
        return False

    # Determine base output dir
    parent_dir = source_path.parent
    output_dir = parent_dir / anime_name / f"Season {season}"
    specials_dir = parent_dir / anime_name / "Specials"
    meta_dir = parent_dir / anime_name / ".meta"

    output_dir.mkdir(parents=True, exist_ok=True)
    specials_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Get episode titles from bangumi_data if available
    ep_titles = {}
    if bangumi_data and "episodes" in bangumi_data:
        for ep in bangumi_data["episodes"]:
            ep_titles[ep.get("ep", 0)] = ep.get("name_cn", "") or ep.get("name", "")

    video_files = sorted([
        f for f in source_path.iterdir()
        if f.is_file() and get_extension(f.name)
    ])

    if not video_files:
        # Maybe files are in subdirectories
        for subdir in source_path.iterdir():
            if subdir.is_dir():
                video_files.extend(sorted([
                    f for f in subdir.iterdir()
                    if f.is_file() and get_extension(f.name)
                ]))

    if not video_files:
        print(f"No video files found in {source_dir}")
        return False

    organized = []
    for src_file in video_files:
        ep_num = extract_episode(src_file.name)
        is_special = detect_is_special(src_file.name)

        ext = get_extension(src_file.name)

        if is_special or ep_num is None:
            # File goes to Specials
            if ep_num:
                new_name = f"{anime_name} - SP{ep_num:02d}{ext}"
            else:
                new_name = f"{anime_name} - SP - {src_file.stem}{ext}"
            target = specials_dir / new_name
        else:
            ep_title = ep_titles.get(ep_num, "")
            if ep_title:
                new_name = f"{anime_name} - S{season:02d}E{ep_num:02d} - {ep_title}{ext}"
            else:
                new_name = f"{anime_name} - S{season:02d}E{ep_num:02d}{ext}"
            target = output_dir / new_name

        # Copy or move file
        if target.exists():
            print(f"  SKIP (exists): {target.name}")
        else:
            shutil.move(str(src_file), str(target))
            print(f"  -> {target.relative_to(parent_dir)}")
            organized.append(str(target.relative_to(parent_dir)))

    # Save source info
    source_info = {
        "source_dir": source_dir,
        "organized_to": str(parent_dir / anime_name),
        "season": season,
        "total_files": len(video_files),
        "organized_files": organized,
        "organize_time": __import__('datetime').datetime.now().isoformat(),
    }
    with open(meta_dir / "organize_info.json", "w", encoding="utf-8") as f:
        json.dump(source_info, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 文件整理完成")
    print(f"   {output_dir.relative_to(parent_dir)}/  ({len([f for f in organized if 'Season' in f])} files)")
    print(f"   {specials_dir.relative_to(parent_dir)}/  ({len([f for f in organized if 'Specials' in f])} files)")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: organize.py <source_dir> <anime_name> <season> [bangumi_json_path]")
        sys.exit(1)

    source_dir = sys.argv[1]
    anime_name = sys.argv[2]
    season = int(sys.argv[3])
    bangumi_data = {}
    if len(sys.argv) > 4:
        bangumi_path = sys.argv[4]
        if os.path.exists(bangumi_path):
            with open(bangumi_path) as f:
                bangumi_data = json.load(f)

    success = organize(source_dir, anime_name, season, bangumi_data)
    sys.exit(0 if success else 1)