#!/usr/bin/env python3
"""用 LocalSend v2.2 协议把文件直发到手机(本机无需安装 LocalSend)。

协议: https://github.com/localsend/protocol
  * 发现: UDP 多播 224.0.0.167:53317。注意官方 App 只在启动时 announce 一次,
    被动收听多半听不到 → 优先用 --ip 直连(或 --scan 扫子网找端口)。
  * 传输: HTTP(S) 端口 53317。手机开「加密」时是 HTTPS + mTLS:
    必须自带客户端证书;fingerprint = 客户端证书 DER 的 SHA-256(大写)。
      POST /api/localsend/v2/register         ← 握手/探测
      POST /api/localsend/v2/prepare-upload   ← 手机弹「接受?」;要 PIN 时需 ?pin=
      POST /api/localsend/v2/upload?sessionId=&fileId=&token=   ← 文件本体

用法:
    python3 localsend_send.py --probe                      # 只发现设备
    python3 localsend_send.py 文件.apkg --ip 192.168.1.5   # 已知手机 IP
    python3 localsend_send.py a.apkg b.pdf --last          # 一次发多个,复用上次设备
    python3 localsend_send.py 文件.apkg --listen 30 --scan # 多播 + 子网扫描
    python3 localsend_send.py 文件.apkg --ip ... --pin 123456

不传 --ip 时:先用上次成功的设备(缓存,6s 探测),失败再走多播 + 子网扫描。
客户端证书首次运行自动生成,放在 ~/.cache/localsend_send/。
手机上把 LocalSend 打开(保持前台),发送时点「接受 / 受信」即可。
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import http.client
import json
import os
import socket
import ssl
import struct
import subprocess
import time
import urllib.parse
import uuid

MCAST_GRP = "224.0.0.167"
MCAST_PORT = 53317
API = "/api/localsend/v2"
PROTO_VERSION = "2.2"
CERT_DIR_DEFAULT = "~/.cache/localsend_send"
LAST_DEVICE = os.path.expanduser("~/.cache/localsend_send/last_device.json")

# 运行时填入 {"crt": ..., "key": ..., "fingerprint": ...}(见 ensure_cert)
CERT: dict[str, str] = {"crt": "", "key": "", "fingerprint": ""}


def ensure_cert(cert_dir: str) -> dict[str, str]:
    """确保自签客户端证书存在(openssl 生成),返回 crt/key/fingerprint。

    LocalSend 开「加密」后是 mTLS:对方要求客户端证书;
    fingerprint = 证书 DER 的 SHA-256(大写,与官方实现一致)。
    """
    crt = os.path.join(cert_dir, "client.crt")
    key = os.path.join(cert_dir, "client.key")
    if not (os.path.exists(crt) and os.path.exists(key)):
        os.makedirs(cert_dir, exist_ok=True)
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048",
             "-keyout", key, "-out", crt, "-days", "3650", "-nodes",
             "-subj", "/CN=LocalSend User"],
            check=True, capture_output=True)
    pem = open(crt).read()
    der = base64.b64decode("".join(
        l.strip() for l in pem.splitlines() if not l.startswith("-----")))
    fp = hashlib.sha256(der).hexdigest().upper()
    return {"crt": crt, "key": key, "fingerprint": fp}


def self_info() -> dict:
    """我们(发送方)的身份信息;fingerprint 来自客户端证书。"""
    return {
        "alias": f"pc-{socket.gethostname()}",
        "version": PROTO_VERSION,
        "deviceModel": "Linux",
        "deviceType": "desktop",
        "fingerprint": CERT["fingerprint"],
        "port": MCAST_PORT,
        "protocol": "https",
        "download": False,
    }


def _mk_conn(ip: str, port: int, scheme: str, timeout: float):
    if scheme == "https":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE          # 自签证书,不校验
        if CERT["crt"]:                          # 加密模式:带上客户端证书
            ctx.load_cert_chain(CERT["crt"], CERT["key"])
        return http.client.HTTPSConnection(ip, port, context=ctx, timeout=timeout)
    return http.client.HTTPConnection(ip, port, timeout=timeout)


def _post(ip: str, port: int, scheme: str, path: str, body: bytes,
          ctype: str, timeout: float):
    conn = _mk_conn(ip, port, scheme, timeout)
    try:
        conn.request("POST", path, body=body,
                     headers={"Content-Type": ctype, "Content-Length": str(len(body))})
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def probe_ip(ip: str, port: int = MCAST_PORT) -> dict | None:
    """已知 IP 时探测(https 优先、http 兜底),返回对方设备信息。"""
    body = json.dumps(self_info()).encode()
    for scheme in ("https", "http"):
        try:
            status, data = _post(ip, port, scheme, f"{API}/register", body,
                                 "application/json", timeout=6)
        except Exception:
            continue
        if status == 200:
            try:
                info = json.loads(data)
            except Exception:
                info = {}
            info.update({"ip": ip, "port": info.get("port") or port,
                         "protocol": info.get("protocol") or scheme})
            return info
    return None


def discover(seconds: float) -> dict[str, dict]:
    """多播发现:被动收 announce,同时每 3s 发一份自己的 announce。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    s.bind(("", MCAST_PORT))
    mreq = struct.pack("4s4s", socket.inet_aton(MCAST_GRP), socket.inet_aton("0.0.0.0"))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(1.0)
    me = self_info()["fingerprint"]
    found: dict[str, dict] = {}
    t0 = time.time()
    last = 0.0
    while time.time() - t0 < seconds:
        if time.time() - last > 3:
            try:
                s.sendto(json.dumps({**self_info(), "announce": True}).encode(),
                         (MCAST_GRP, MCAST_PORT))
            except OSError:
                pass
            last = time.time()
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        try:
            info = json.loads(data.decode("utf-8"))
        except Exception:
            continue
        if not isinstance(info, dict) or "fingerprint" not in info:
            continue
        if str(info["fingerprint"]) == me:
            continue                              # 自己的多播回环
        fp = str(info["fingerprint"])
        if fp not in found:
            info["ip"] = addr[0]
            info.setdefault("protocol", "https")
            info.setdefault("port", MCAST_PORT)
            found[fp] = info
            print(f"  发现 {info.get('alias', '?')} | {info.get('deviceModel', '?')}"
                  f" | {info.get('deviceType', '?')} | {addr[0]}:{info['port']}"
                  f" | {info.get('protocol')}")
    s.close()
    return found


def scan_subnet(port: int = MCAST_PORT) -> list[dict]:
    """多播被挡时的兜底:扫本 /24 网段的 TCP <port>,再逐个 register 拿信息。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
    except OSError:
        return []
    finally:
        s.close()
    prefix = my_ip.rsplit(".", 1)[0]

    def open_port(ip: str) -> str | None:
        try:
            with socket.create_connection((ip, port), timeout=0.4):
                return ip
        except OSError:
            return None

    hosts = [f"{prefix}.{i}" for i in range(1, 255)]
    alive: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
        for res in ex.map(open_port, hosts):
            if res:
                alive.append(res)
    devs: list[dict] = []
    for ip in alive:
        info = probe_ip(ip, port)
        if info:
            devs.append(info)
            print(f"  发现 {info.get('alias', '?')} | {info.get('deviceModel', '?')}"
                  f" | {info.get('deviceType', '?')} | {ip}:{info.get('port')}")
    if not devs:
        print(f"  {prefix}.0/24 上没有可用的 LocalSend")
    return devs


def _find(listen_s: float, do_scan: bool, port: int) -> list[dict]:
    print(f"[discover] 多播监听 {listen_s:.0f}s …(手机上请先打开 LocalSend)")
    devs = list(discover(listen_s).values())
    if not devs and do_scan:
        print(f"[scan] 多播无果,扫本网段 {port} 端口找设备 …")
        devs = scan_subnet(port)
    return devs


def load_last() -> dict | None:
    """上次发送成功的设备(IP 可能因 DHCP 变化,调用方仍需 probe 确认)。"""
    try:
        with open(LAST_DEVICE, encoding="utf-8") as fh:
            dev = json.load(fh)
        return dev if dev.get("ip") else None
    except Exception:
        return None


def save_last(dev: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LAST_DEVICE), exist_ok=True)
        with open(LAST_DEVICE, "w", encoding="utf-8") as fh:
            json.dump(dev, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def send(dev: dict, paths: list[str], pin: str = "") -> int:
    ip = dev["ip"]
    port = int(dev.get("port") or MCAST_PORT)
    scheme = dev.get("protocol") or "https"
    files: dict[str, dict] = {}
    payloads: list[tuple[str, dict, bytes]] = []
    for path in paths:
        with open(path, "rb") as fh:
            payload = fh.read()
        fid = uuid.uuid4().hex[:8]
        finfo = {
            "id": fid,
            "fileName": os.path.basename(path),
            "size": len(payload),
            "fileType": "application/octet-stream",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        files[fid] = finfo
        payloads.append((fid, finfo, payload))
    total = sum(len(p) for _, _, p in payloads)
    print(f"→ 发送 {len(payloads)} 个文件({total / 1e6:.1f} MB)到 "
          f"{dev.get('alias', ip)}({ip}:{port}, {scheme})")
    for _, finfo, _ in payloads:
        print(f"  - {finfo['fileName']}({finfo['size'] / 1e6:.1f} MB)")
    print("  请在手机上点「接受 / 受信」…")
    body = json.dumps({"info": self_info(), "files": files}).encode()
    path_up = f"{API}/prepare-upload" + (f"?pin={urllib.parse.quote(pin)}" if pin else "")
    try:
        status, data = _post(ip, port, scheme, path_up, body,
                             "application/json", timeout=180)
    except Exception as e:                        # noqa: BLE001
        print(f"  ✘ prepare-upload 失败: {e}")
        return 2
    if status == 401:
        print("  ✘ 手机设置了 PIN:用 --pin 123456 重跑,或先在手机上关掉 PIN")
        return 3
    if status != 200:
        print(f"  ✘ 被拒绝或出错: HTTP {status} {data[:200]!r}")
        return 3
    res = json.loads(data)
    session = res["sessionId"]
    tokens = res["files"]
    print("  已接受,上传中…")
    for fid, finfo, payload in payloads:
        q = urllib.parse.urlencode(
            {"sessionId": session, "fileId": fid, "token": tokens[fid]})
        try:
            status, data = _post(ip, port, scheme, f"{API}/upload?{q}", payload,
                                 "application/octet-stream", timeout=600)
        except Exception as e:                    # noqa: BLE001
            print(f"  ✘ 上传 {finfo['fileName']} 失败: {e}")
            return 4
        if status not in (200, 204):
            print(f"  ✘ 上传 {finfo['fileName']} 出错: HTTP {status} {data[:200]!r}")
            return 5
    save_last(dev)
    print(f"✔ 完成。手机 LocalSend 的下载目录里会出现这 {len(payloads)} 个文件")
    return 0



def resolve_device(a) -> dict | None:
    """确定目标设备:--ip > 上次成功设备 > 多播 > 子网扫描。"""
    if a.ip:
        dev = probe_ip(a.ip, a.port)
        if not dev:
            print(f"✘ {a.ip}:{a.port} 上没有可用的 LocalSend")
        return dev

    if a.last:
        last = load_last()
        if not last:
            print("✘ 还没有成功发送过的设备;先不带 --last 跑一次")
            return None
        dev = probe_ip(last["ip"], int(last.get("port") or a.port))
        if not dev:
            print(f"✘ 上次的设备 {last['ip']} 已不可达(DHCP 变了?),去掉 --last 重新发现")
        return dev

    if not a.refresh and not a.match:
        last = load_last()
        if last:
            dev = probe_ip(last["ip"], int(last.get("port") or a.port))
            if dev:
                print(f"[cache] 复用上次设备 {dev.get('alias', last['ip'])} ({dev['ip']})")
                return dev

    devs = _find(a.listen, a.scan, a.port)
    if not devs:
        print("没发现设备。检查:手机 LocalSend 是否已打开、是否同一 Wi-Fi。")
        return None
    if a.match:
        devs = [d for d in devs if a.match.lower() in
                (str(d.get("alias", "")) + str(d.get("deviceModel", ""))).lower()]
        if not devs:
            print(f"没有匹配 {a.match!r} 的设备")
            return None
    mobiles = [d for d in devs if d.get("deviceType") == "mobile"]
    candidates = mobiles or devs
    if len(candidates) > 1:
        print("发现多台候选设备:")
        for d in candidates:
            print(f"  - {d.get('alias')} / {d.get('deviceModel')}"
                  f" / {d.get('deviceType')} / {d.get('ip')}")
        print("用 --match 指定别名后重跑。")
        return None
    return candidates[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="LocalSend(v2)直发文件到手机")
    ap.add_argument("files", nargs="*", help="要发的文件(可多个)")
    ap.add_argument("--probe", action="store_true", help="只发现设备,不发送")
    ap.add_argument("--listen", type=float, default=10, help="多播监听秒数(默认 10)")
    ap.add_argument("--ip", default="", help="已知对方 IP(跳过多播发现)")
    ap.add_argument("--port", type=int, default=MCAST_PORT)
    ap.add_argument("--match", default="", help="按别名/型号子串挑设备")
    ap.add_argument("--scan", action="store_true",
                    help="多播无果时扫本子网 53317(路由器挡多播时的兜底)")
    ap.add_argument("--last", action="store_true",
                    help="只用上次发送成功的设备(不重新发现)")
    ap.add_argument("--refresh", action="store_true",
                    help="忽略缓存设备,强制重新发现")
    ap.add_argument("--pin", default="", help="对方要求 PIN 时用")
    ap.add_argument("--cert-dir", default=CERT_DIR_DEFAULT,
                    help="客户端证书目录(默认 ~/.cache/localsend_send)")
    a = ap.parse_args()

    CERT.update(ensure_cert(os.path.expanduser(a.cert_dir)))
    print(f"[cert] {CERT['crt']} fp={CERT['fingerprint'][:16]}…")

    if a.probe or not a.files:
        if a.ip:
            dev = probe_ip(a.ip, a.port)
            if not dev:
                print(f"✘ {a.ip}:{a.port} 上没有可用的 LocalSend")
                return 1
            print(f"  发现 {dev.get('alias', '?')} | {dev.get('deviceModel', '?')}"
                  f" | {dev.get('deviceType', '?')} | {a.ip}:{dev.get('port')}")
            return 0
        if a.last or a.refresh or a.match:
            dev = resolve_device(a)
            return 0 if dev else 1
        devs = _find(a.listen, a.scan, a.port)
        if not devs:
            print("没听到任何设备。检查:手机 LocalSend 是否已打开、是否同一 Wi-Fi。")
            return 1
        return 0 if a.probe else 1

    for path in a.files:
        if not os.path.exists(path):
            print(f"文件不存在: {path}")
            return 1

    dev = resolve_device(a)
    if not dev:
        return 1
    return send(dev, a.files, pin=a.pin)


if __name__ == "__main__":
    raise SystemExit(main())
