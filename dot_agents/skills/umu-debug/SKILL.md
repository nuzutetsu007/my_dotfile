---
name: umu-debug
description: 调试 umu-launcher / Proton / Wine prefix / 游戏存档问题的完整工作流。凡是用户提到 umu、umu-run、GE-Proton、UMU-Proton、steamrt、protonfixes、winetricks、WINE prefix、Proton 日志报错、游戏存档迁移/合并、runner 冲突，或给出 umu/Proton 的启动日志要解读，都必须使用本 skill——即使只是问"我的 proton 装在哪"或"这个日志是什么意思"。
---

# umu-debug：umu-launcher 调试工作流

本 skill 沉淀自 2026-10 的一次真实排障：从 man 文档 → 环境变量溯源 → runner 盘点 →
prefix/存档迁移 → 日志解读的完整链路。目标系统为 Arch + fish + systemd user env +
Niri，但流程通用。

## 第 0 步：先跑体检脚本

```bash
bash <skill目录>/scripts/umu-report.sh
```

一次性输出：PROTONPATH 解析结果、环境变量来源（fish 通用变量 + systemd 用户环境）、
全部 runner 清单及大小、prefix 清单及版本、legacy 残留。**先看这份报告再动手**，
后续步骤只是对报告中异常项的深挖。

## 1. 文档优先

- `man umu`（umu(1)）：用法 + 全部环境变量默认值
- `man umu 2>/dev/null` 实际会解析到 umu(1)；配置文件页单独看：
  `zcat /usr/share/man/man5/umu.5.gz`（TOML `--config`，[umu] 表）
- 源码（行为与 man 不一致时以源码为准）：
  `python3 -c 'import umu.umu_run as m, os; print(os.path.dirname(m.__file__))'`
  关键文件 `umu_proton.py`（下载/版本解析）、`umu_run.py`（prefix 构建）

### 文档默认值速查（必背）

| 变量 | 默认 |
|---|---|
| `PROTONPATH` | 未设 → 自动下载最新 **UMU-Proton** 到 `~/.local/share/Steam/compatibilitytools.d/` |
| `WINEPREFIX` | 未设 → `$HOME/Games/umu/$GAMEID`；无 GAMEID → `~/Games/umu/umu-default` |
| `GAMEID` | 未设 → `umu-default`（不套任何 protonfix） |
| `PROTON_VERB` | `waitforexitandrun` |
| HTTP | timeout 5s / retries 3（`UMU_HTTP_TIMEOUT` / `UMU_HTTP_RETRIES`） |

## 2. 环境变量溯源（umu 问题 80% 出在这里）

按优先级检查三层，注意**旧拷贝不一致**：

```bash
# ① fish 通用变量（--export 才会传给子进程！）
grep SETUVAR ~/.config/fish/fish_variables | grep -iE 'proton|wine|umu|gameid'

# ② systemd 用户环境（经 import-environment 传播给整个会话）
systemctl --user show-environment | grep -iE 'PROTON|WINE|UMU|GAMEID'

# ③ 当前进程继承（判断"新改的值为何不生效"）
env | grep -iE 'PROTON|WINE|UMU'
```

**关键陷阱**：
- fish 里 `set -Ux` 有 `--export`；`set -U`（无 x）**不会**导出，是隐形死变量
- fish 的 path 类型变量（fish_variables 里标 `--path`）直接 `set -Ux VAR 值` 会被
  当路径处理而**清空**，必须先 `set -e VAR` 再重建
- 改完 fish 变量后要 `systemctl --user import-environment <VAR>` 刷新 systemd 拷贝；
  已开着的进程仍持有旧值，需重开会话

## 3. PROTONPATH 解析逻辑（源码 `_fetch_latest`）

`PROTONPATH` 是 codename（如 `GE-Proton`）而非路径时：
1. **每次启动请求 GitHub releases/latest**，发现更新的版本直接下载（SHA512 校验）
2. 网络失败时 fallback：在 `compatibilitytools.d/` 里 glob `GE-Proton*`，按
   **自然排序取 max**（数字段按数值比，11-7 > 11-3）
3. 因此手动装的旧版 GE-Proton 一旦有新版存在就永远是死重量；但 umu 对 GE 目录
   **只增不删**（man 页说的"自动移除旧版"仅指 UMU-Proton）
4. `compatibilitytools.d/LegacyRuntime` 是 Steam 运行时组件，**不是 runner，不能删**

## 4. Prefix 解剖与存档

```
~/Games/umu/<GAMEID>/          # 默认 prefix 布局
├── version                    # prefix 版本标记（升级时被改写）
├── config_info                # 创建它的 runner 信息
├── winetricks.log             # 用 winetricks 装过的组件
└── drive_c/users/steamuser/   # 存档 90% 在这里：
    ├── AppData/Roaming/       # 大多数日系游戏（SHIBASOFT、KiriKiri 等）
    ├── AppData/Local/         # 部分游戏 + rmmz-game(RPGMaker MZ) 等
    ├── Documents/             # ENTERGRAM、KID、5pb 系等
    └── Saved Games/           # 新式 API 存档位
```

**存档合并标准流程**（先 diff 找差异，再复制，再校验）：

```bash
# 1. 找出旧 prefix 里"非模板"的实际存档（按时间过滤）
find <旧prefix>/drive_c/users -type f -newermt 2026-01-01 | grep -viE 'Templates|Favorites|\.lnk$|Temp/|Crashpad|ShaderCache'
# 2. 复制（GNU cp 对已存在的目标目录会把内容并进去，不套层）
cp -a <旧prefix>/drive_c/users/steamuser/AppData/Roaming/X <新prefix>/drive_c/users/steamuser/AppData/Roaming/
# 3. 校验（目标已有内容属正常差异，排除后 diff）
diff -r <src> <dst> && echo "完全一致 ✓"
```

- 存档位置也可查 protonfixes 数据库或 PCGamingWiki per-game 页面
- 合并完不要立刻删旧 prefix——留着当备份，游戏内读档确认后再删

## 5. 日志解读速查表

用 `UMU_LOG=debug umu-run ...` 拿全量日志，常见条目：

| 日志 | 定性 |
|---|---|
| `No GAMEID set, using umu-default` | 正常，纯默认行为 |
| `GE-Proton is up to date` / `Downloading GE-Proton11-7... SHA512 is OK` | codename 自动更新机制，正常 |
| `Running '<runner>' using runtime 'steamrt4'` | runner 解析成功 |
| `Upgrading prefix from X to Y` | 换 runner 后的一次性 prefix 升级，正常 |
| `Prefix has an invalid version?! You may want to back up...` | 升级流程的标准提示（版本文件还是旧值），**跟着升级继续跑就是无害的**，但提示备份是真的——先备份再动 |
| `Error: unable to use parent for game drive, path /home` | exe 放太浅（父目录是 $HOME），Proton 拒绝建游戏盘符映射；**一般无害**，把 exe 放进独立目录（如 `~/Games/xxx/`）可消除 |
| `WARN: Game title not found in CSV` / `No protonfix found` | 无 GAMEID 时查不到专属修复，属正常；游戏需要修复就设 `GAMEID=umu-xxx` |
| `WARN: Game drive creation failed` 类 | 真问题，检查 exe 路径与权限 |

## 6. 冒烟测试（不碰用户 prefix）

```bash
env -i HOME=$HOME PATH=/usr/bin:/usr/sbin UMU_LOG=debug \
  WINEPREFIX=/tmp/umu-test PROTONPATH=GE-Proton umu-run "" 2>&1 | \
  grep -iE 'GE-Proton|UMU-Proton|runtime|ERROR|WARN'
# "" = 只建空 prefix 不跑游戏；完了 rm -rf /tmp/umu-test
```

看三件事：解析出哪个 runner、是否下载了新版本、prefix 是否成功创建。

## 7. winetricks

```bash
PROTONPATH=GE-Proton WINEPREFIX=<prefix> umu-run winetricks <verb>
```
要求 GE-Proton 或 UMU-Proton（纯 Steam Proton 不带 winetricks 支持）。
装过的 verb 记录在 prefix 的 `winetricks.log`。

## 8. 清理守则（删除前必读）

- ✅ 可删：codename 解析下永远不会被选中的旧版 GE-Proton；确认不用的 Bottles/Lutris
  runner（`~/.local/share/bottles/runners/`、`~/.local/share/lutris/runners/`）
- ❌ 别删：`LegacyRuntime`；`steamapps/common/` 下的 Steam 官方 Proton（有 Steam 游戏
  引用它时删了会启动失败——先在 Steam 里把游戏切走）
- 删 runner 前先 `du -sh` 确认目标，`ls` 确认路径里没有同名目录风险

## 9. 磁盘全景盘点

```bash
ls -d ~/.local/share/Steam/compatibilitytools.d/*/ \
      ~/.local/share/Steam/steamapps/common/*[Rr]oton* \
      ~/.local/share/bottles/runners/*/ \
      ~/.local/share/lutris/runners/*/*/ \
      ~/.local/share/Trash/files/*[Rr]oton* 2>/dev/null
# 注意：回收站里的 "Proton Mail.desktop"、"wine-extension-*.desktop" 是垃圾文件不是 runner
# Bottles 的 runner Steam/umu 看不到，反之亦然——按"服务对象"归类
```