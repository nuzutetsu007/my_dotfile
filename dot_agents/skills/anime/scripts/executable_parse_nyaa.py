#!/usr/bin/env python3
"""
Parse Nyaa.si HTML search results.
Usage: parse_nyaa.py <html_file>
Output: JSON array
"""
import sys
import re
import json
import html


def parse_nyaa_html(data: str) -> list:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', data, re.DOTALL)
    results = []
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 8:
            continue
        # Title
        title_match = re.search(
            r'<a[^>]*href="[^"]*"[^>]*>(.*?)</a>', cells[1], re.DOTALL
        )
        if not title_match:
            continue
        title = html.unescape(re.sub(r'<[^>]+>', '', title_match.group(1)).strip())

        # Magnet / Torrent links in cells[2]
        magnet = ''
        torrent_url = ''
        magnet_match = re.search(r'href="(magnet:[^"]+)"', cells[2])
        if magnet_match:
            magnet = magnet_match.group(1)
        torrent_match = re.search(r'href="(/download/[^"]+)"', cells[2])
        if torrent_match:
            torrent_url = 'https://nyaa.si' + torrent_match.group(1)

        # Size - plain text in cells[3]
        size = cells[3].strip()

        # Seeders / Leechers - plain text
        seeders = int(cells[5].strip()) if cells[5].strip().isdigit() else 0
        leechers = int(cells[6].strip()) if cells[6].strip().isdigit() else 0

        results.append({
            'source': 'nyaa',
            'title': title,
            'size': size,
            'seeders': seeders,
            'leechers': leechers,
            'magnet': magnet,
            'torrent_url': torrent_url,
        })
    return results


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: parse_nyaa.py <html_file>"}))
        sys.exit(1)
    with open(sys.argv[1], encoding='utf-8', errors='replace') as f:
        data = f.read()
    results = parse_nyaa_html(data)
    print(json.dumps(results, ensure_ascii=False, indent=2))