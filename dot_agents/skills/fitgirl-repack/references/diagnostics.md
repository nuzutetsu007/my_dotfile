# 诊断手册：FitGirl 安装器卡住 / 报错

核心原则：**先取证，再动手。** 一次错误的重装要花 35 分钟 + 66GB 写入；
而三组 `/proc` 数据 15 秒就能定性。

## 0. 先确定卡在哪一阶段

```bash
systemctl --user status <unit>          # Active / Result=oom-kill
journalctl --user -u <unit> -n 50
pgrep -a -f 'setup.tmp|cls-magic2|CLS-srep|oo2recm|xtool'
tail -5 <repack>/install-inno.log
```

| 现象 | 阶段 | 含义 |
|---|---|---|
| 只有 Inno 日志，无 `setup.tmp` | A 失败 | 外壳都没跑完：路径、权限、Wine 环境 |
| `setup.tmp` 在，子进程是 `cls-magic2`/`CLS-srep`/`oo2recm`/`xtool` | B 解压中 | 正常，看进度和 I/O |
| `setup.tmp` 在，但子进程都没了 | B 收尾 | 可能在处理可选内容或跑 vc_redist |
| `setup.tmp` 不在，目录体积稳定 | 可能已完成 | 直接做 md5 校验，别急着重装 |
| 进程不在，unit `Result=oom-kill` | OOM | 加 swap 重跑 |

`install-inno.log` 里的 `Installation process succeeded` 是**阶段 A** 的结束语，
不是安装完成。别被它骗。

## 1. 取证三件套

```bash
P=$(pgrep -x setup.tmp | head -1)

# ① 还在干活吗（隔 10 秒取两次）
awk -F'[: ]+' '/^rchar/{print "rchar",$2}/^wchar/{print "wchar",$2}' /proc/$P/io

# ② 开着哪些值得注意的文件
ls -l /proc/$P/fd 2>/dev/null \
  | grep -vE 'pipe:|socket:|anon_inode|/dev/|memfd' \
  | awk '{print $(NF-2), $NF}'

# ③ 线程是在等锁还是空转
for t in /proc/$P/task/*; do
  printf '%s wchan=%s ticks=%s\n' "$(basename "$t")" \
    "$(cat "$t/wchan" 2>/dev/null)" \
    "$(awk '{print $14+$15}' "$t/stat" 2>/dev/null)"
done | sort -t= -k3 -rn | head
```

判读：

| 证据 | 结论 |
|---|---|
| 标题不变 + r/w ≈ 0 + **恰好一个线程 wchan=0 且 ticks 飞涨**，其余 `futex_wait_multiple` | **死循环**（bug，不是在算） |
| 标题不变 + 全部 `futex`/`poll_schedule_timeout` + I/O 0 | 在等外部事件：隐藏对话框、锁、磁盘 |
| I/O 有量、CPU 有量，只是标题不更新 | 正常，标题刷新粒度粗 |
| `rchar` 涨但 `wchar` 不涨 | 在读输入、卡在解码/写盘前 |

死循环的典型触发：**读到一个半截的 `fg-optional-*.bin`**。特征非常固定：
fd 里开着该文件、单线程 100% CPU、零 I/O、进度停在 94% 附近（收尾阶段）。

## 2. 症状 → 处理

### 2.1 进度标题长时间不动

1. 跑第 1 节三件套。
2. 若判定死循环：
   - **先校验游戏本体**（`fg-verify.sh`），很多情况下文件已经全了；
   - 校验通过 → 杀掉安装器，直接启动；
   - 校验失败 → 清理 `game/` 重装（见第 3 节）。
3. 若在等对话框：枚举所有窗口，找不可见的 modal：

```bash
for id in $(xdotool search --name '' 2>/dev/null); do
  echo "$id | $(xdotool getwindowname "$id" 2>/dev/null)"
done
grim /tmp/screen.png && tesseract /tmp/screen.png - -l eng+jpn --psm 3 | head -30
```

静默参数理论上不该有对话框；有就说明参数没生效（检查是否真的传给了
`setup.exe`，而不是被 shell 吃掉）。

### 2.2 进程消失 / `Result=oom-kill`

```bash
dmesg | grep -iE 'killed process|out of memory' | tail -5
journalctl --user -u <unit> | grep -i 'oom\|killed'
```

FitGirl 解压峰值实测 ~9.4GB（`cls-magic2` 单进程 RSS 7.3–7.6GB）。
RAM 16G 且无 swap 也会被内核挑出来杀。处理：

```bash
sudo fallocate -l 16G /home/swap/swapfile
sudo chmod 600 /home/swap/swapfile
sudo mkswap /home/swap/swapfile
sudo swapon /home/swap/swapfile
echo '/home/swap/swapfile none swap defaults 0 0' | sudo tee -a /etc/fstab
```

重跑前确认 `free -h` 里 swap 真的挂上了。

### 2.3 `ISDone.dll` / `unarc.dll` 报错

这两类错误码是 FitGirl 的万能背锅位，真实原因按概率排序：

1. **分卷不完整/损坏** —— 先校验分卷：

```bash
cd "<repack>/MD5"
tr -d '\r' < fitgirl-bins.md5 | grep -v '^;' | sed 's#\\#/#g' > /tmp/bins.md5
LC_ALL=C md5sum -c --quiet /tmp/bins.md5
```

   （清单同样是 CRLF + `..\`，且有 `;` 注释行，直接 `-c` 会报格式错误。）

2. **内存不足** —— 见 2.2，加 swap。
3. **临时目录空间不足** —— `%TEMP%` 在 prefix 里，prefix 和安装目录可能不同盘；
   两处都要留 ≥10G。
4. **路径太长 / 非 ASCII / 权限** —— 换成短 ASCII 路径重试，例如
   `/home/<user>/Games/<slug>/game`，避开中文、空格、超长目录名。
5. **Wine 版本/前缀损坏** —— 换一个干净 prefix（删掉重建），或换 runner。
6. **杀毒/索引** —— Linux 上少见，但 btrfs 快照/索引服务会拖慢；可忽略。

处理顺序就是 1→6，每步只改一个变量。

### 2.4 解压很慢

按影响排序：

```bash
powerprofilesctl get                       # power-saver = 1.3GHz，慢 3 倍+
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
findmnt -no OPTIONS --target <安装目录>     # compress=zstd ?
vmstat 2 5                                  # si/so 高 = swap 抖动
sensors 2>/dev/null | grep -i package       # 95°C+ 会降频
```

- `power-saver` → `powerprofilesctl set balanced`（或 performance）。
- btrfs `compress=zstd` → 安装目录 `chattr +C`（只对新文件生效，要重装才有效）。
- swap 抖动 → 关掉占内存的程序；swap 在 NVMe 上比 HDD 好得多。
- 温度墙 → 垫高/清灰/限 PL，别在解压时跑别的重负载。

实测：同一次安装，1.3GHz 时 232MB/min，3.8GHz 时 ~11.8GB/min。

### 2.5 装完但游戏起不来

按顺序查：

1. **文件完整性** —— `fg-verify.sh`，249/249 才继续。
2. **VC 运行库** —— FitGirl 收尾会跑 `_Redist/vc_redist.x64.exe`；静默模式下可能没跑：

```bash
umu-run "<game>/_Redist/vc_redist.x64.exe" /install /quiet /norestart
```

3. **图形栈** —— `nvidia-smi` 有输出、`vulkaninfo --summary` 正常；
   Xwayland + NVIDIA 下 GLX 报 `BadValue` 时加 `__GLX_VENDOR_LIBRARY_NAME=mesa`。
4. **prefix 架构** —— 64 位游戏用 64 位 prefix（默认就是）。
5. **日志** —— `journalctl --user -u <unit>` 找
   `Unhandled page fault`、`d3d12`、`vkd3d`、`dxgi` 关键字。
6. **GAMEID** —— 需要 protonfix 的游戏设 `GAMEID=umu-<id>`；
   不知道就先用 `umu-default`，能跑就别动。

`Error: unable to use parent for game drive, path /home` 是无害警告，
原因是 exe 的父目录是 `$HOME`；把游戏放进独立子目录即可消失。

### 2.6 怎么确认"其实已经装完"

三个条件同时满足：

- `game/` 里有主 exe，且根目录 `*.forge` 体积在 2 分钟内不变；
- 没有 `setup.tmp` / `cls-magic2` / `xtool` 在跑；
- `fg-verify.sh` 全部通过。

`game/temp-fitgirl/`、`game/srep-virtual-memory.tmp` 是正常残留，不影响运行，
校验通过后可以删。

## 3. 重启安装的正确姿势

```bash
systemctl --user stop <unit>
pgrep -a -f 'setup.tmp|cls-magic2|CLS-srep|oo2recm|xtool'   # 确认没残留
```

清理：

```bash
rm -rf "<game>"/*                    # 保留目录本身（chattr +C 标记还在）
rm -rf "$WINEPREFIX/drive_c/users/steamuser/AppData/Local/Temp/is-"*.tmp
```

重跑前再确认：

- 所有 `fg-0x.bin` 大小与种子一致；**半截的 optional bin 要么补完、要么删掉**；
- swap 已挂载、电源档位不是 power-saver；
- 安装目录在 btrfs 上已 `chattr +C`；
- 路径是短 ASCII。

然后 `fg-install.sh` 重跑。

## 4. 命令速查

```bash
# 进度（标题就是进度条）
for id in $(xdotool search --name '%'); do echo "$id $(xdotool getwindowname $id)"; done

# 采样
bash scripts/fg-watch.sh 15 "<game>"

# 存活
P=$(pgrep -x setup.tmp|head -1)
cat /proc/$P/io; ls -l /proc/$P/fd | tail -20

# 线程
for t in /proc/$P/task/*; do echo "$(basename $t) $(cat $t/wchan) $(awk '{print $14+$15}' $t/stat)"; done

# 死因
systemctl --user status <unit>
dmesg | grep -i 'killed process' | tail

# 校验
bash scripts/fg-verify.sh "<game>"
```

## 5. 别做这些事

- **别在没校验前重装**：66GB 写入 + 35 分钟，可能只是收尾卡住而已。
- **别点 Cancel**：Inno 的取消可能触发清理，半成品状态更难判断。
- **别在解压中删 `game/` 里的文件**：会直接破坏正在写的管线。
- **别信 Inno 日志的 "succeeded"**：那只代表外壳阶段。
- **别同时改多个变量**：加 swap、换 runner、改路径一起上，出问题就不知道是谁的锅。
