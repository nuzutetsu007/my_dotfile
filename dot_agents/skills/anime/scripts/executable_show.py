#!/usr/bin/env python3
"""
显示搜索结果的表格视图。
Usage: search_mikan.sh "keyword" | show.py
       search_nyaa.sh "keyword" | show.py
Stdin: JSON array of resources
"""
import sys, json, subprocess, shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

def parse_title(title):
    """调用 parse_title.py 解析标题"""
    r = subprocess.run(
        ['python3', str(SCRIPT_DIR / 'parse_title.py'), title],
        capture_output=True, text=True
    )
    return json.loads(r.stdout) if r.returncode == 0 else {}

rows = json.load(sys.stdin)
if not rows:
    print("无结果")
    sys.exit(0)

term_w = shutil.get_terminal_size().columns

# 标题列宽 = 终端宽 - 其他列占用
for r in rows[:20]:
    m = parse_title(r['title'])
    src = r.get('source', '?')
    group = m.get('sub_group') or '?'
    ep = m.get('episode')
    ep_str = f'EP{ep:02d}' if ep else '?'
    seeds = r.get('seeders', '?')
    # seeders 可能不存在 (mikan)
    seeds_str = f'{seeds:>3}s' if isinstance(seeds, int) else '  -'
    codec = m.get('codec') or '?'
    sub_lang = m.get('subtitle_lang') or '?'
    size = r.get('size', '')

    # 构建一行
    prefix = f'[{group:>12}] {ep_str} | {seeds_str} | {codec:5} | {sub_lang:10} | {size:>10} | '
    remain = term_w - len(prefix) - 1
    title_short = r['title'][:remain] if remain > 20 else r['title'][:50]
    print(f'{prefix}{title_short}')