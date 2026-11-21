---
name: localsend
description: Send files from this Linux PC directly to the user's phone over the LocalSend v2.2 protocol, with no LocalSend app, GUI, or cloud service on the PC. Use whenever the user says 发到手机, 传到手机, 发送到手机, 传给我手机, send to my phone, send this to my iPhone/Android, share/transfer a file to the phone, "用 LocalSend 发", "像 AirDrop 一样传", or asks to push an .apkg/.epub/.pdf/image/video to their phone. Handles device discovery (multicast plus subnet scan), HTTPS mutual TLS, PIN, multiple files per session, and remembering the last device.
---

# LocalSend

Push files to the user's phone over the LAN using the LocalSend protocol. The PC needs no LocalSend install: this skill speaks the protocol directly (`scripts/localsend_send.py`, stdlib only).

**Requirement on the phone side:** the LocalSend app must be open and in the foreground. iOS suspends it when backgrounded, and then port 53317 stops answering. If discovery fails, ask the user to open LocalSend, then retry.

## Quick start

```bash
S=~/.agents/skills/localsend/scripts/localsend_send.py

python3 "$S" --probe                       # discover devices (multicast, then subnet scan)
python3 "$S" report.pdf                    # send, reusing the last device if reachable
python3 "$S" a.apkg b.pdf c.epub           # several files in one session (single accept)
python3 "$S" movie.mp4 --last              # only the last successful device, no discovery
python3 "$S" file.zip --ip 192.168.0.184   # known IP, skips discovery entirely
python3 "$S" file.zip --pin 123456         # phone has a PIN enabled
```

Discovery order when `--ip` is absent: cached last device (6 s probe) → multicast 10 s → subnet scan (only with `--scan`). Use `--refresh` to ignore the cache, `--match <alias>` to pick between several devices.

The user must tap **接受 / Accept** on the phone. `prepare-upload` blocks up to 180 s waiting for that tap; the upload itself gets 600 s.

## Options

| Option | Meaning |
|---|---|
| `--probe` | List devices, send nothing |
| `--ip <ip>` | Target directly; skip discovery (recommended when known) |
| `--last` | Use only the last successful device |
| `--refresh` | Ignore the cached device |
| `--match <substr>` | Filter by alias or device model |
| `--scan` | Fall back to scanning the local /24 on port 53317 |
| `--listen <s>` | Multicast listen seconds (default 10) |
| `--pin <pin>` | PIN when the phone returns HTTP 401 |
| `--cert-dir <dir>` | Client certificate location |

Exit codes: `0` sent, `1` discovery/file problem, `2` connect or prepare-upload failure, `3` rejected or PIN required, `4` upload connection failure, `5` upload HTTP error.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `没有可用的 LocalSend` / no devices | Phone app must be open and foregrounded; same Wi-Fi; guest/AP isolation blocks it; retry with `--scan` |
| Works one minute, fails the next | iOS backgrounded the app; ask the user to reopen it |
| HTTP 401 | PIN enabled on the phone: ask the user for the PIN, use `--pin` |
| Rejected / HTTP 403 | User tapped decline, or the file list changed; just retry |
| Cached device unreachable | DHCP moved the phone: drop `--last`, use `--refresh` or `--ip` |
| Multiple devices found | Ask which one, then `--match "<alias>"` |
| `prepare-upload` timeout | No tap within 180 s; rerun and ask the user to accept |

If several phones/PCs answer, never guess: list them for the user and ask.

## Protocol notes

- Discovery: UDP multicast `224.0.0.167:53317`; devices announce only at app start, so active probing and subnet scan matter.
- API base: `/api/localsend/v2`; `register` → `prepare-upload` → `upload`.
- With encryption enabled the phone serves HTTPS with a self-signed cert and requires **client** certificates. The script generates one at `~/.cache/localsend_send/client.{crt,key}` (10-year validity) and advertises `fingerprint` = SHA-256 of the DER certificate, uppercase — the same value the official client uses.
- TLS verification is intentionally disabled (self-signed, LAN-only). Do not send over untrusted networks.
- Last successful device is cached in `~/.cache/localsend_send/last_device.json`; delete it to forget devices.

## Rules

- Send only files the user asked for; verify paths exist before sending.
- Keep transfers on the LAN; this script never uploads to the internet.
- Do not delete or regenerate the client certificate unless it is corrupted — the phone may remember the fingerprint.
- Report the phone's alias/IP and each filename after a successful send.
- Original script lives in `~/code/anki-grammer/src/localsend_send.py`; the copy under `scripts/` is the maintained skill version.
