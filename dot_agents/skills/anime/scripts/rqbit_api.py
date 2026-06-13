#!/usr/bin/env python3
"""
rqbit API 封装 — CLI 管理服务端 + 种子

用法:
  python rqbit_api.py server start <output_dir>   启动服务
  python rqbit_api.py server stop                 停止服务
  python rqbit_api.py server status               查看状态
  python rqbit_api.py torrent list                列出任务
  python rqbit_api.py torrent add <torrent_path>  添加 .torrent 文件/URL
  python rqbit_api.py batch <task.json> [dir]     批量添加
  python rqbit_api.py summary                     进度总览

依赖: curl, rqbit
工作流: search_nyaa.sh → curl 下 .torrent 到 /tmp → rqbit_api.py 上传
"""

import json, os, subprocess, sys, time, urllib.request, signal
from pathlib import Path

API = "http://127.0.0.1:3030"
PIDFILE = "/tmp/rqbit-server.pid"
LOGFILE = "/tmp/rqbit-server.log"
PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""


def api_get(path):
    return json.loads(urllib.request.urlopen(f"{API}{path}", timeout=10).read())


def curl_upload(filepath):
    """POST .torrent 文件到 rqbit API。用 curl 避免编码问题。"""
    url = f"{API}/torrents?overwrite=true"
    with open(filepath, "rb") as f:
        r = subprocess.run(
            ["curl", "-s", "--data-binary", "@-", url],
            stdin=f, capture_output=True, timeout=30,
        )
    out = r.stdout.decode(errors="replace")
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr.decode(errors="replace")[:80]}
    try:
        d = json.loads(out)
        ih = d.get("info_hash") or d.get("details", {}).get("info_hash", "?")
        return {"ok": True, "name": d.get("name", "?"), "info_hash": ih}
    except json.JSONDecodeError:
        return {"ok": False, "error": f"bad JSON: {out[:80]}"}


def torrent_stats(infohash):
    s = api_get(f"/torrents/{infohash}/stats/v1")
    total = s.get("total_bytes", 0)
    done = s.get("progress_bytes", 0)
    pct = (done / total * 100) if total > 0 else 0
    sym = "✅" if s.get("finished") else "⏳"
    speed = ""
    ds = s.get("live", {}).get("download_speed", {})
    if ds.get("human_readable"):
        speed = f" @ {ds['human_readable']}"
    return f"{sym} {pct:5.1f}%{speed}"


# ─── server ───

def cmd_server(args):
    if args[0] == "start":
        if Path(PIDFILE).exists():
            print("already running")
            return
        outdir = args[1]
        os.makedirs(outdir, exist_ok=True)
        env = os.environ.copy()
        if PROXY:
            env["HTTP_PROXY"] = env["HTTPS_PROXY"] = PROXY
        proc = subprocess.Popen(
            ["rqbit", "server", "start", outdir],
            stdout=open(LOGFILE, "w"), stderr=subprocess.STDOUT,
            env=env, preexec_fn=os.setsid,
        )
        Path(PIDFILE).write_text(str(proc.pid))
        for _ in range(10):
            time.sleep(1)
            try:
                urllib.request.urlopen(f"{API}/", timeout=2)
                print(f"started (pid {proc.pid})")
                return
            except Exception:
                pass
        print("timeout")
    elif args[0] == "stop":
        try:
            pid = int(Path(PIDFILE).read_text())
            os.kill(pid, signal.SIGTERM)
            Path(PIDFILE).unlink(missing_ok=True)
            print("stopped")
        except Exception:
            print("not running")
    elif args[0] == "status":
        try:
            d = api_get("/")
            print(f"running  v{d.get('version','?')}  pid={Path(PIDFILE).read_text().strip()}")
        except Exception:
            print("not running")


# ─── torrent ───

def cmd_torrent(args):
    if args[0] == "list":
        try:
            for t in api_get("/torrents").get("torrents", []):
                print(f"  {t['info_hash'][:16]}  {t['name'][:50]}")
        except Exception as e:
            print(f"error: {e}")
    elif args[0] == "add":
        fpath = args[1]
        if fpath.startswith("http"):
            tmp = f"/tmp/torrent_{int(time.time())}.torrent"
            env = os.environ.copy()
            if PROXY:
                env["http_proxy"] = env["https_proxy"] = PROXY
            subprocess.run(["curl", "-sL", "-o", tmp, fpath], env=env, timeout=30)
            fpath = tmp
        r = curl_upload(fpath)
        if r["ok"]:
            print(f"  ✅ {r['name'][:50]} [{r['info_hash'][:16]}]")
        else:
            print(f"  ❌ {r.get('error','?')}")


# ─── batch ───

def cmd_batch(args):
    task_file = args[0]
    outdir = args[1] if len(args) > 1 else os.getcwd()
    with open(task_file) as f:
        data = json.load(f)
    tasks = data.get("tasks", data if isinstance(data, list) else [])

    cmd_server(["start", outdir])

    for task in tasks:
        url = task.get("url") or task.get("torrent_url", "")
        magnet = task.get("magnet", "")
        name = task.get("name", "?")

        if url:
            if os.path.exists(url):
                r = curl_upload(url)
            else:
                tmp = f"/tmp/torrent_{int(time.time())}.torrent"
                env = os.environ.copy()
                if PROXY:
                    env["http_proxy"] = env["https_proxy"] = PROXY
                subprocess.run(["curl", "-sL", "-o", tmp, url], env=env, timeout=30)
                r = curl_upload(tmp)
        elif magnet:
            mfile = f"/tmp/magnet_{int(time.time())}.txt"
            Path(mfile).write_text(magnet)
            r2 = subprocess.run(
                ["curl", "-s", "-d", f"@{mfile}", f"{API}/torrents?overwrite=true"],
                capture_output=True, timeout=30,
            )
            try:
                d = json.loads(r2.stdout)
                r = {"ok": True, "name": d.get("name", "?"), "info_hash": d.get("info_hash", "?")}
            except Exception:
                r = {"ok": False, "error": r2.stderr.decode()[:60]}
        else:
            r = {"ok": False, "error": "no url/magnet"}

        sym = "✅" if r.get("ok") else "❌"
        detail = r.get("info_hash", r.get("error", "?"))[:16]
        print(f"  {sym} {name} [{detail}]")

    print(f"\n  API: {API}/web/")


# ─── summary ───

def cmd_summary():
    try:
        for t in api_get("/torrents").get("torrents", []):
            s = torrent_stats(t["info_hash"])
            print(f"  {s}  {t['name'][:50]} [{t['info_hash'][:16]}]  {t.get('output_folder','')}")
    except Exception as e:
        print(f"error: {e}")


# ─── main ───

CMDS = {
    "server": cmd_server,
    "torrent": cmd_torrent,
    "batch": cmd_batch,
    "summary": lambda _: cmd_summary(),
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd in CMDS:
        CMDS[cmd](sys.argv[2:])
    else:
        print(f"unknown: {cmd}")
        sys.exit(1)
