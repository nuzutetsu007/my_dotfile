#!/usr/bin/env python3
"""
Parse anime torrent/resource title to extract metadata.
Usage: echo "<title>" | python3 parse_title.py
   or: python3 parse_title.py "<title>"

Output: JSON with extracted fields
"""
import json
import re
import sys


def parse_title(title: str) -> dict:
    result = {
        "raw_title": title,
        "sub_group": None,
        "episode": None,
        "episode_count": None,
        "resolution": None,
        "source": None,
        "codec": None,
        "audio": None,
        "subtitle_lang": None,
        "is_collection": False,
        "is_bd": False,
        "is_batch": False,
        "version": None,
    }

    # Sub group - typically at start in brackets
    sub_match = re.match(r'^[\[\(]([^\]\)]+)[\]\)]', title)
    if sub_match:
        result["sub_group"] = sub_match.group(1).strip()

    # Resolution
    res_patterns = [
        r'(\d{3,4}[pPiI])', r'(4K)', r'(2160p)', r'(1080p)', r'(720p)',
        r'(\d+x\d+)'
    ]
    for p in res_patterns:
        m = re.search(p, title, re.IGNORECASE)
        if m:
            result["resolution"] = m.group(1).upper()
            break

    # Source tags
    source_map = {
        'Baha': 'Bahamut', 'CR': 'Crunchyroll', 'AT-X': 'AT-X',
        'WEB-DL': 'WEB-DL', 'WebRip': 'WebRip', 'BD': 'BD',
        'BDRip': 'BDRip', 'DVD': 'DVD', 'TV': 'TV', 'RAW': 'RAW'
    }
    for key, val in source_map.items():
        if re.search(r'\b' + re.escape(key) + r'\b', title, re.IGNORECASE):
            result["source"] = val
            break

    # Codec - use [\W_]+ separator since codec names often in brackets with underscores
    codec_map = {
        'x265': 'x265', 'HEVC': 'HEVC', 'h265': 'H265',
        'x264': 'x264', 'AVC': 'AVC', 'h264': 'H264',
        'AV1': 'AV1'
    }
    codec_keys = sorted(codec_map.keys(), key=len, reverse=True)  # longer first
    for key in codec_keys:
        # Match with word boundary, underscore, or bracket boundary
        if re.search(r'(?:^|[\W_])' + re.escape(key) + r'(?:$|[\W_])', title, re.IGNORECASE):
            result['codec'] = codec_map[key]
            break

    # Audio
    audio_map = {
        'FLAC': 'FLAC', 'AAC': 'AAC', 'MP3': 'MP3', 'OPUS': 'Opus',
        'AC3': 'AC3', 'EAC3': 'EAC3', 'DTS': 'DTS', 'TrueHD': 'TrueHD'
    }
    for key, val in audio_map.items():
        if re.search(r'\b' + re.escape(key) + r'\b', title, re.IGNORECASE):
            result["audio"] = val
            break

    # Subtitle language
    sub_lang_map = {
        r'简\s*繁': 'CHS&CHT',
        r'CHS\s*[&+]\s*CHT': 'CHS&CHT',
        r'CHT\s*[&+]\s*CHS': 'CHS&CHT',
        r'简繁': 'CHS&CHT',
        r'繁简': 'CHS&CHT',
        r'\bCHS\b': 'CHS',
        r'\bCHT\b': 'CHT',
        r'繁(?:体|體)?': 'CHT',
        r'简(?:体|體)?': 'CHS',
        r'\bBIG5\b': 'CHT',
        r'\bGB\b': 'CHS',
        r'\bJPN\b': 'JPN',
        r'\bENG\b': 'ENG',
        r'\bMulti\b': 'Multi',
    }
    for pattern, lang in sub_lang_map.items():
        m = re.search(pattern, title, re.IGNORECASE)
        if m:
            result['subtitle_lang'] = lang
            break
    # Episode number
    # Chained patterns: try most specific first
    ep = None
    ep_count = None

    # 1. Full range with EP prefix: EP01-12
    range_match = re.search(r'[Ee][Pp]?\s*(\d+)\s*[-~]\s*(\d+)', title)
    if range_match:
        ep = int(range_match.group(1))
        ep_count = int(range_match.group(2))
    else:
        # 2. Plain digit range: 01-24 or 01~24 (common in anime titles)
        plain_range = re.search(r'(?<![\d])(\d{2})[-~](\d{2})(?![\d])', title)
        if plain_range:
            a, b = int(plain_range.group(1)), int(plain_range.group(2))
            if 1 <= a <= b <= 999:
                ep = a
                ep_count = b

    if ep_count:
        result['episode'] = ep
        result['episode_count'] = ep_count
        result['is_collection'] = True
    else:
        # 3. EP prefix single
        ep_match = re.search(r'[Ee][Pp]?\s*(\d+)', title)
        if ep_match:
            result['episode'] = int(ep_match.group(1))
        else:
            # 4. 第XX話 / 第XX集
            cn_match = re.search(r'第\s*(\d+)\s*[話话集]', title)
            if cn_match:
                result['episode'] = int(cn_match.group(1))
            else:
                # 5. Standalone number after dash - common: ' - 05 '
                dash_num = re.search(r'[-–]\s*(\d{1,3})(?=\s*\[|\s*$|\s*-)', title)
                if dash_num:
                    n = int(dash_num.group(1))
                    if 1 <= n <= 999:
                        result['episode'] = n
                else:
                    # 6. Vol.X or vX
                    vol_match = re.search(r'\b[Vv][Oo][Ll]?\.?\s*(\d+)', title)
                    if vol_match:
                        result['episode'] = int(vol_match.group(1))

    # Batch / Collection
    if re.search(r'\b(Batch|全集|合集|Complete|Full)\b', title, re.IGNORECASE):
        result["is_collection"] = True
        result["is_batch"] = True

    # BD / Blu-ray
    if re.search(r'\b(BD|Blu[-\s]?ray|BDRip)\b', title, re.IGNORECASE):
        result["is_bd"] = True

    # Version (v2, v3 etc)
    ver_match = re.search(r'[Vv](\d+)\b', title)
    if ver_match:
        result["version"] = int(ver_match.group(1))

    return result


if __name__ == "__main__":
    title = sys.stdin.read().strip() if len(sys.argv) < 2 else sys.argv[1]
    if not title:
        print(json.dumps({"error": "no title provided"}))
        sys.exit(1)
    result = parse_title(title)
    print(json.dumps(result, ensure_ascii=False, indent=2))