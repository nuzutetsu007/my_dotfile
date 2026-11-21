---
name: fitgirl-repack
description: 在 Linux 上用 umu-launcher + GE-Proton 安装、校验、启动 FitGirl（及同类 Inno+ISDone）重打包游戏，并在安装器卡住/报错时定位真正原因。凡是用户提到 FitGirl、repack、fitgirl.md5、setup.exe 配 fg-0x.bin、ISDone.dll、unarc.dll、cls-magic2、CLS-srep、oo2recm、xtool、"装到 94% 不动了"、"解压报错"、"装完打不开"，或要把 Windows 游戏的 repack 装到 Linux / Steam Deck 上，都必须使用本 skill——即使他们没说 "FitGirl" 这三个字。
---

# fitgirl-repack：在 Linux 上装 FitGirl 重打包游戏

沉淀自 2026-11 一次真实安装（AC 黑旗 记忆重置，66GB，35 分钟解压）：
Inno 静默安装 → 四段解压管线 → 卡在 94.8% 的死循环诊断 → md5 全量校验 → umu 启动。

核心心态：**安装器是个黑盒 GUI，但它的状态全在 `/proc` 和窗口标题里。**
不要点它，去读它。

## 0. 先跑体检，别急着双击

```bash
REPACK_DIR="<repack目录>" bash <skill目录>/scripts/fg-preflight.sh <安装目标目录>
```

一次输出：内存/swap、目标盘剩余空间与文件系统、CPU 电源档位与实际频率、
btrfs 压缩状态、umu/Proton 可用性、GLX 环境、分卷完整性。
**这些项每一项都能单独把安装搞死**，先看报告再决定要不要开跑。

判读要点：

| 项 | 红线 | 处理 |
|---|---|---|
| swap | 无 swap 且 RAM < 16G | 建 16G swapfile，否则解压峰值 ~9.4G 会被 OOM kill |
| 空间 | 剩余 < 安装后大小 + 10G | FitGirl 需要 repack 体积 + 解压体积 + 临时文件 |
| 电源档位 | `power-saver` | 频率被钉在 1.3GHz，解压慢 3 倍以上；`powerprofilesctl set balanced` |
| btrfs | `compress=zstd` | 写入放大 + CPU 开销；安装目录先 `chattr +C`（只对新文件生效） |
| GLX | Xwayland + nvidia 且 glxinfo 报错 | `__GLX_VENDOR_LIBRARY_NAME=mesa` |

## 1. 认清三个阶段（决定你该等多久、该看哪里）

FitGirl 的 `setup.exe` 是 Inno Setup 外壳 + 自研解包器，**三段完全不同**：

**阶段 A：Inno 壳（几秒）**
把 `ISDone.dll`、`arc.ini`、`setup.tmp`、`xtool.exe` 等解到
`%TEMP%\is-XXXX.tmp\`，写 `unins000.*`、`_Redist/`、快捷方式。
`install-inno.log` 末尾出现 `Installation process succeeded` **只代表这一段结束**，
不代表游戏装好了——这是最容易误判的地方。

**阶段 B：FitGirl 解包（几十分钟，吃满 CPU）**
`setup.tmp` 通过 `ISDone.dll` + `arc.ini` 读 `fg-0x.bin`，四段管道**串行**：

```
fg-01.bin → cls-magic2_x64 → CLS-srep_x64 → oo2recm → xtool decode → game/
```

串行意味着最慢一段决定全局，所以 CPU 频率、swap、磁盘压缩的影响是乘性的。
细节见 `references/pipeline.md`。

**阶段 C：收尾**
删 `srep-virtual-memory.tmp`、解可选内容（原声带/预告片/配音包）、跑 `vc_redist`。

## 2. 下载：只下要的，且要能续

```bash
aria2c --seed-time=0 --bt-max-peers=200 \
  --dir="download/<Repack 名>" \
  --input-file=<只含需要文件的 .txt> \
  <torrent 或 magnet>
```

- 先只下 `setup.exe` + `fg-01..0N.bin`；`fg-optional-*` 按需。
- **可选分卷要么完整、要么删掉**。半截的 `fg-optional-*.bin` 会让安装器在收尾阶段
  死循环（实测卡在 94.8%，单线程 100% CPU、零 I/O）。
- 断点续传：`aria2c -c --dir=... <torrent>`；控制文件 `*.aria2` 别乱删。
- 种子里的 `MD5/fitgirl-bins.md5` 用来校验**分卷**，和装完后的
  `game/_Redist/fitgirl.md5`（校验**游戏文件**）不是一回事。它同样是 CRLF + `..\`
  相对路径，还多一行 `;` 注释，直接 `md5sum -c` 会报格式错误：

```bash
cd "<repack>/MD5"
tr -d '\r' < fitgirl-bins.md5 | grep -v '^;' | sed 's#\\#/#g' > /tmp/bins.md5
LC_ALL=C md5sum -c --quiet /tmp/bins.md5
```

## 3. 安装：静默 + 脱离会话

```bash
bash <skill目录>/scripts/fg-install.sh "<repack 目录>" "<安装目录>" [unit 名]
```

脚本做的事（也可手抄）：

```bash
systemd-run --user --unit=acbf-install --collect \
  --working-directory="$REPACK" \
  --setenv=HOME="$HOME" --setenv=DISPLAY=:0 \
  --setenv=WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=GAMEID=umu-default \
  --setenv=WINEPREFIX="$HOME/Games/umu/<slug>" \
  --setenv=PROTONPATH="$HOME/.local/share/Steam/compatibilitytools.d/GE-ProtonXX-Y-x86_64" \
  --setenv=__GLX_VENDOR_LIBRARY_NAME=mesa \
  "$(command -v umu-run)" ./setup.exe \
    /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /CLOSEAPPLICATIONS \
    "/DIR=Z:\home\<user>\Games\<...>\game" \
    "/LOG=Z:\home\<user>\Games\<...>\install-inno.log"
```

关键点：

- `/DIR=` 必须写成 **Wine 的 `Z:` 盘路径**（`Z:\home\...`），反斜杠；
  umu 把 `/` 映射为 `Z:`，写 unix 路径 Inno 会当成相对路径。
- 用 `systemd-run --user` 而不是 `nohup`：关终端/断 SSH 不会带走安装，
  `systemctl --user status <unit>` 还能看 `Result=oom-kill` 这类死因。
- `__GLX_VENDOR_LIBRARY_NAME=mesa` 是 Xwayland + NVIDIA 下 GLX `BadValue`
  的解法；Wine 窗口建不出来时先验证 `umu-run notepad` 能弹窗。
- 静默模式下 Inno 不弹问题框，所以**"报错"往往只是一个卡住的进度条**。

## 4. 盯着它：读标题，不读像素

FitGirl 的进度窗口是 **1×1 的隐藏窗口**，百分比和 ETA 写在**窗口标题**里：

```bash
for id in $(xdotool search --name '%' 2>/dev/null); do
  echo "$id | $(xdotool getwindowname "$id")"
done
# 44040195 | 94.8%   00:01:54
```

`bash <skill目录>/scripts/fg-watch.sh 15 <安装目录>` 会把这条信息连同
`/proc/<pid>/io`、线程 `wchan`、目录体积打成一行的采样，自动标记 STALL。

需要看画面时才截图 + OCR（`grim` + `tesseract`），别用鼠标：

```bash
grim -g "x,y WxH" /tmp/dlg.png
tesseract /tmp/dlg.png - -l eng+jpn --psm 6
```

## 5. 卡住了？按证据分诊，别猜

按顺序取三组证据，结论基本就唯一了：

```bash
P=$(pgrep -x setup.tmp | head -1)          # 或 pgrep -f setup.tmp

# ① 还在干活吗
awk -F'[: ]+' '/^rchar|^wchar/{print $1,$2}' /proc/$P/io   # 隔 10s 再取一次

# ② 它开着哪些"不该开"的文件
ls -l /proc/$P/fd | grep -vE 'pipe:|socket:|anon_inode|/dev/|memfd'

# ③ 线程在等锁还是在空转
for t in /proc/$P/task/*; do
  echo "$(basename $t) $(cat $t/wchan) $(awk '{print $14+$15}' $t/stat)"
done
```

| 证据组合 | 结论 | 处理 |
|---|---|---|
| 标题不动 + 零 I/O + **单线程 wchan=0 且 ticks 猛涨**，其余 futex | 死循环（常见：半截可选 bin） | 杀掉；先 md5 校验，再决定重装 |
| 标题不动 + 零 I/O + 全部 futex/`poll` | 在等外部东西（磁盘/网络/弹窗） | 查 fd、`dmesg`、是否有隐藏对话框 |
| 进度慢但 I/O 正常 | CPU 频率或磁盘压缩 | 查 `powerprofilesctl get`、`scaling_cur_freq` |
| 进程消失、unit `Result=oom-kill` | 内存不够 | `dmesg \| grep -i 'killed process'`，加 swap 重跑 |
| 弹出 `ISDone.dll` / `unarc.dll` 错误框 | 内存、空间、路径、权限 | 看 `install.log` 与 `%TEMP%` 下日志；换短 ASCII 路径 |

**杀之前先校验**。解压常常在收尾阶段卡住，但游戏文件已经全了：

```bash
bash <skill目录>/scripts/fg-verify.sh "<安装目录>"
```

249 个文件 / 66GB 在 NVMe 上约 70–90 秒。全 OK 就可以直接启动，不必重装。
完整决策树见 `references/diagnostics.md`。

## 6. 校验：fitgirl.md5 有三个坑

`game/_Redist/fitgirl.md5` 是 **CRLF + 反斜杠 + `..\` 相对路径**，
而且路径相对于 `_Redist/`。直接 `md5sum -c` 会得到 0 个 OK。

```bash
cd "<安装目录>/_Redist"
tr -d '\r' < fitgirl.md5 | sed 's#\\#/#g' > /tmp/fg.md5
LC_ALL=C md5sum -c --quiet /tmp/fg.md5   # 只打印失败项，退出码非 0 即有问题
```

脚本 `fg-verify.sh` 已处理这些，并统计 OK/失败数量。

注意：中文 locale 下 `md5sum` 输出是「完了」而不是 `OK`，写判断逻辑时
用**退出码**或 `LC_ALL=C`，别 grep 英文单词。

## 7. 启动：umu + 桌面项

```bash
bash <skill目录>/scripts/fg-run.sh "<安装目录>" [exe]
```

等价于：

```bash
cd "<安装目录>"
GAMEID=umu-default \
WINEPREFIX="$HOME/Games/umu/<slug>" \
PROTONPATH="$HOME/.local/share/Steam/compatibilitytools.d/GE-ProtonXX-Y-x86_64" \
__GLX_VENDOR_LIBRARY_NAME=mesa \
umu-run ./Game.exe
```

后台跑（推荐，日志可查）：

```bash
systemd-run --user --unit=<game> --collect \
  --setenv=DISPLAY=:0 --setenv=WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" --setenv=HOME="$HOME" \
  bash <skill目录>/scripts/fg-run.sh "<安装目录>"
```

验证真的进游戏了，而不是只看进程活着：

```bash
niri msg windows | grep -A3 'Title'      # 或 xdotool search --name ''
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
grim /tmp/game.png && tesseract /tmp/game.png - -l eng+jpn --psm 3 | head
```

看到标题变成游戏名、GPU 有占用、截图里有菜单/校准页，才算成功。
`Error: unable to use parent for game drive, path /home` 一般无害，
把 exe 放进独立目录即可消除。

桌面项（可选）：

```ini
[Desktop Entry]
Type=Application
Name=<游戏名>
Exec=/usr/bin/env bash /path/to/run.sh
Path=/path/to/game
Icon=applications-games
Terminal=false
Categories=Game;
```

## 8. 收尾与清理

装完先确认，再删东西：

- ✅ 可删：`game/temp-fitgirl/`、`game/srep-virtual-memory.tmp`（2GB 级残留）、
  `*.aria2`、临时日志、半截的 optional bin。
- ⚠️ 保留：`download/` 里的 `fg-0x.bin`（补可选内容/重装要用，35GB 量级），
  直到你确认游戏稳定运行。
- ❌ 别删：`game/_Redist/`（含 `fitgirl.md5`，日后校验的唯一依据）。

## 9. 性能速查（按影响排序）

1. **CPU 电源档位**：`power-saver` → 1.3GHz；`balanced/performance` → 3.8GHz+。
   实测吞吐 232MB/min → 11.8GB/min，比任何参数调整都重要。
2. **swap**：无 swap 时 `cls-magic2` 峰值 9.4GB 直接被 OOM；16GB swapfile 足够。
3. **btrfs 压缩**：`compress=zstd` 对 66GB 顺序写是纯负担；安装目录 `chattr +C`。
4. **磁盘**：NVMe 与 SATA SSD 差一倍以上；别装到网络盘/USB。
5. **并行度**：管线是串行的，加线程无用；`xtool -t100p` 已吃满。

## 参考

- `references/pipeline.md` — 四段解压管线、各段资源特征、文件布局
- `references/diagnostics.md` — 卡住/报错的完整决策树与 `/proc` 取证命令
- `scripts/fg-preflight.sh` — 装前体检
- `scripts/fg-install.sh` — 静默安装（systemd-run）
- `scripts/fg-watch.sh` — 进度 + 存活采样
- `scripts/fg-verify.sh` — fitgirl.md5 全量校验
- `scripts/fg-run.sh` — umu 启动
