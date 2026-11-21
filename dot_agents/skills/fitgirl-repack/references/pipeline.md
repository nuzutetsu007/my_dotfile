# FitGirl 解压管线与资源特征

## 阶段 A：Inno Setup 外壳

`setup.exe` 是 Inno Setup（FitGirl 常用 5.5.x）打包的安装器。启动后先把载荷解到：

```
%TEMP%\is-XXXXXX.tmp\
├── setup.tmp            # 真正的解包器（阶段 B 的主角）
├── ISDone.dll           # 调外部压缩器的桥
├── arc.ini              # 压缩器命令行定义
├── CLS-srep.dll/.exe    # SREP 解码器
├── cls-magic2.dll/.exe  # 外层压缩解码器
├── cls-lollypop*.exe
├── oo2recm.exe          # oo2rec 解码
├── xtool.exe            # 游戏资源解码
├── precomp*.exe / fbz / mpz.exe / nz.exe / reflate.exe / pZLib
├── BASS.dll / music.mp3 # 安装时播的背景音乐
└── _isetup\             # 图标等
```

这一段几秒到几十秒，产物是 `unins000.exe/.dat`、`_Redist/`（vc_redist、dxwebsetup、
`fitgirl.md5`）、开始菜单/桌面快捷方式。日志末尾的
`Installation process succeeded` 只标志这一段。

## 阶段 B：四段串行管线

`arc.ini` 把每个 `fg-0x.bin` 的压缩方法映射到外部命令。实际执行链：

```
fg-01.bin
  │  ISDone.dll 读取 + 调度
  ▼
cls-magic2_x64.exe d     外层压缩（CLS 魔改 LZMA），单进程吃满多核
  │  stdout pipe
  ▼
CLS-srep_x64.exe d       SREP 长程冗余，基本单线程，写 srep-virtual-memory.tmp
  │  stdout pipe
  ▼
oo2recm.exe d            oo2rec/doodle 解码
  │  stdout pipe
  ▼
xtool.exe decode -t100p -dm50p    游戏资源解码（forge/贴图/音频）
  │
  ▼
game/
```

关键性质：

- **串行**：同一时刻只有一段在跑，吞吐由最慢一段决定。加线程不会让它更快。
- **时钟敏感**：SREP 段接近单线程，CPU 频率从 3.8GHz 掉到 1.3GHz，整条管线
  慢 3 倍以上（实测 11.8GB/min → 232MB/min）。
- **内存尖峰**：`cls-magic2` 单进程 RSS 可达 7.3–7.6GB，系统峰值 ~9.4GB；
  没有 swap 的 16G 机器会被 OOM。
- **临时文件**：SREP 会写 `srep-virtual-memory.tmp`（约 2GB，在安装目录），
  结束/中断后残留，可删。

### 怎么判断当前在哪一段

```bash
pgrep -a -f 'cls-magic2|CLS-srep|oo2recm|xtool'
```

| 子进程 | 段 | 资源特征 |
|---|---|---|
| `cls-magic2_x64` | 外层解压 | 多核、内存最高 |
| `CLS-srep_x64` | SREP | 单线程、写 2GB 临时文件、最慢 |
| `oo2recm` | 重编码 | 中等 CPU、大 I/O |
| `xtool` | 资源解码 | 多线程（`-t100p`）、写最终文件 |

### 进度从哪来

FitGirl 的进度窗口是一个 **1×1 的隐藏窗口**，标题形如：

```
94.8%   00:01:54
```

`xdotool getwindowname <id>` 直接读，不需要截图。ETA 只在阶段 B 有效，
收尾阶段可能停住不动——这正是要结合 I/O 和线程状态判断的原因。

## 阶段 C：收尾

1. 删 `srep-virtual-memory.tmp`、`temp-fitgirl/`；
2. 解可选内容（原声带、预告片、额外配音）——**这一步最容易死循环**，
   因为安装器会去读 `fg-optional-*.bin`；文件半截就会卡住；
3. 跑 `_Redist/vc_redist.x64.exe`（静默模式可能被跳过，必要时手动补）；
4. 写快捷方式、卸载器。

## 安装后的目录长什么样

```
game/
├── <Game>.exe                 # 主程序
├── DataPC_*.forge             # 游戏资源档案（最大的几个，几 GB~几十 GB）
├── D3D12/                     # D3D12 核心库
├── NVStreamline/              # DLSS/DLSS-FG
├── _Redist/
│   ├── fitgirl.md5            # 全量校验清单（249 项量级）
│   ├── vc_redist.x64.exe
│   └── dxwebsetup.exe
├── unins000.exe / .dat
└── temp-fitgirl/              # 收尾残留，可删
```

`.forge` 是 AC 系列（AnvilNext）的资源包，体积巨大但都是顺序写，
所以磁盘顺序写性能和压缩设置影响很大。

## 性能模型（实测数据，AC 黑旗 66GB）

| 条件 | 吞吐 |
|---|---|
| `power-saver`（1.3GHz，powersave governor） | ~232 MB/min |
| `balanced/performance`（3.7–3.9GHz） | ~11.8 GB/min |
| 无 swap、峰值 9.4GB | 13:46 被 OOM kill |
| 16GB swap | 峰值 11.2GB used + 5.1GB swap，跑完 |

时间线（供估算）：

```
13:51  阶段 A 结束
13:55  1.1 GB
14:04  26.8 GB
14:20  50.7 GB
14:26  66 GB（阶段 B 完成）
```

也就是说 **~35 分钟 / 66GB** 是 3.8GHz + NVMe 的正常水平。
如果显著慢于这个量级，先查电源档位和 btrfs 压缩，而不是怀疑种子。

## 调优清单（按收益）

1. `powerprofilesctl set balanced`（或 performance）——收益最大。
2. 16GB swap（或 ≥16GB RAM）——避免 OOM。
3. 安装目录 `chattr +C`（btrfs）——去掉 CoW/压缩开销。
4. 装到 NVMe，别用 USB/网络盘。
5. 关掉占内存的浏览器/游戏，减少 swap 抖动。
6. 不要试图改 `-t100p`：已经吃满；`-dm50p` 是内存缓冲比例，
   内存紧张时可尝试更低，但 FitGirl 已按分卷调好，改动风险大于收益。
