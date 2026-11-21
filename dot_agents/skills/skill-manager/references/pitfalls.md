# 已知陷阱与处理

## 1. 体积

`machine` 这类 skill 会带 `node_modules`（19 MB）、示例视频、字体包，整体能到几十 MB。放公共目录不会让各 agent 变慢——它们启动时只索引 SKILL.md 的 frontmatter，body 和资源是触发后才读——但会拖慢 dotfiles 同步和备份。

处理：确认 `node_modules` 是可重建的（有 `package.json` + lockfile）就删掉，让 skill 首次使用时自己装；或者给 dotfiles 加 `.gitignore` / chezmoi 的 `.chezmoiignore`。

```bash
printf '**/node_modules\n' > ~/.agents/skills/machine/.chezmoiignore
```

## 2. 软链

早期为了让 pi 看到公共目录的 skill，会在 `~/.pi/agent/skills/` 里建软链。pi 现在原生读 `~/.agents/skills`，这些软链变成重复来源：同名 skill 被加载两次，行为取决于谁后加载。

判断：`ls -l <agent私有目录>`，看到 `-> ../../../.agents/skills/xxx` 的就是残留，删掉软链本身（`rm` 不带 `-r`，别把目标也删了）。

## 3. 硬编码路径

搬迁时最容易漏的一类。skill 里常见三种写法：

| 写法 | 是否要改 |
|---|---|
| `~/.config/opencode/skills/foo/scripts/run.sh` | 要改 |
| `scripts/run.sh`（相对 skill 根目录） | 不用改，harness 会告诉模型 base dir |
| README 里"上游推荐这样安装：`git clone ... ~/.claude/skills/foo`" | 不改，那是文档不是运行路径 |

改完用 `grep -rn` 复查，确保零命中。脚本文件（`.sh` `.py` `.mjs`）也要一起 grep——SKILL.md 里写对了、脚本里写错的情况很常见。

## 4. dotfiles 管理

`~/.agents/skills` 常被 chezmoi / stow / 手写 git 仓库接管。搬运前先确认：

```bash
chezmoi managed | grep '^\.agents/skills'   # 只列出被托管的条目
```

- 被托管的条目（例如 `anime`）不要 `mv`，要在 dotfiles 源目录里操作，再 `chezmoi apply`。
- 未被托管的（`chezmoi add` 没做过）随便搬，`chezmoi apply` 不会碰它们，但也不会备份。
- 新搬完想纳入管理：`chezmoi add ~/.agents/skills/<name>`。注意这把整个目录（含 node_modules）纳入，先按第 1 条瘦身。

如果 `~/.agents/skills` 目录本身被托管，`chezmoi apply` 只补源里声明的文件，不会删除你手动放进去的 skill——但仍建议显式 add，否则换机器就丢。

## 5. 同名冲突

两个不同来源的 skill 重名时，谁生效取决于目录扫描顺序，且不会报错。所以搬运前必须查：

```bash
ls -d ~/.agents/skills/*/ | xargs -n1 basename | sort | uniq -d
```

真冲突了就改名（改目录名 + frontmatter 的 `name`，两者保持一致），不要靠"反正另一个不常用"。

## 6. 项目级 vs 用户级

`<repo>/.agents/skills/` 里的 skill 只在该仓库生效。把项目级 skill 搬到用户级会让它在所有仓库都出现，通常不是你想要的——除非它本来就是通用工具。搬之前问一句"这个只在那个项目里用吗"。

## 7. 通过 CLI 装的 vs 手放的

`~/.agents/.skill-lock.json` 只记录 CLI 装的（`npx skills add`）。手放的显示 `untracked`：

- `npx skills update` 不会更新它们
- `npx skills remove` 也删不掉它们，得 `rm -rf`
- 想在多台机器同步，只能靠 dotfiles

这是正常的，不是错误。但如果一个 skill 明确来自某个 GitHub 仓库，用 CLI 重装一遍反而更省事——以后 `update` 能自动跟进。
