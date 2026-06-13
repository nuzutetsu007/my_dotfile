#!/usr/bin/env python3
"""
Parse Mikan Project HTML search results.
Usage: parse_mikan.py <html_file>
Output: JSON array
"""
import sys
import re
import json
import html as html_mod


def parse_mikan_html(data: str) -> list:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', data, re.DOTALL)
    results = []
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 3:
            continue

        # Magnet from checkbox input data-magnet attribute
        magnet = ''
        magnet_match = re.search(r'data-magnet="(magnet:[^"]+)"', cells[0])
        if magnet_match:
            # Decode HTML entities in magnet URL
            magnet = html_mod.unescape(magnet_match.group(1))

        # Title
        title = ''
        title_match = re.search(
            r'class="magnet-link-wrap"[^>]*>(.*?)</a>',
            cells[1], re.DOTALL
        )
        if title_match:
            title = html_mod.unescape(re.sub(r'<[^>]+>', '', title_match.group(1)).strip())

        if not title and not magnet:
            continue

        # Size
        size = cells[2].strip() if len(cells) > 2 else ''

        # Date
        date = cells[3].strip() if len(cells) > 3 else ''

        # Torrent download link
        torrent_url = ''
        if len(cells) > 4:
            torrent_match = re.search(r'href="(/Download/[^"]+)"', cells[4])
            if torrent_match:
                torrent_url = 'https://mikan.tangbai.cc' + torrent_match.group(1)

        results.append({
            'source': 'mikan',
            'title': title,
            'size': size,
            'date': date,
            'magnet': magnet,
            'torrent_url': torrent_url,
        })
    return results


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: parse_mikan.py <html_file>"}))
        sys.exit(1)
    with open(sys.argv[1], encoding='utf-8', errors='replace') as f:
        data = f.read()
    results = parse_mikan_html(data)
    print(json.dumps(results, ensure_ascii=False, indent=2))