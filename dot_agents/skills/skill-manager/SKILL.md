---
name: skill-manager
description: 管理 agent skill 本身——安装、搬运、去重、审计、更新、卸载，以及让同一份 skill 被多个 agent（opencode / pi / claude-code / codex / antigravity / gemini-cli）共用。只要用户提到 npx skills、skills add/remove/list/update、"把 skill 搬到公共目录"、"统一管理 skill"、"两个 agent 都想用这个 skill"、"skill 装了但不生效 / 没被识别 / 重复出现"、"新机器上恢复我的 skill"、或者让你安装某个 GitHub 仓库里的 SKILL.md，都要用本 skill——即使他们没说"skill 管理"这几个字。
---

# Skill Manager

一句话原则：**用户级 skill 只存在一个目录里，其他 agent 都去读它。** 不要为了"让 A 也能看到"而复制一份到 A 的私有目录，那是后面所有麻烦的源头。

## 唯一权威位置

| 作用域 | 路径 | 谁读它 |
|---|---|---|
| 用户级 | `~/.agents/skills/<name>/SKILL.md` | opencode、pi、antigravity、gemini-cli（均原生读取） |
| 项目级 | `<repo>/.agents/skills/<name>/SKILL.md` | 同上，但只在该仓库内生效 |

各 agent 的私有目录（`~/.config/opencode/skills/`、`~/.pi/agent/skills/`、`~/.claude/skills/`）**保持为空**。它们是历史遗留入口，东西放进去就只有那一家能看到。

判断依据不用猜：agent 的二进制里能搜到 `userAgentsSkillsDir` 之类的常量，或者直接跑一次（见下面的"验证"）。

## 安装

```bash
# 看仓库里有哪些 skill，先别装
npx skills add <owner>/<repo> -l --full-depth

# 装到公共目录，并登记给多个 agent
npx skills add <owner>/<repo> -g -a opencode -a pi --skill <name> -y

# 仓库根目录没有 SKILL.md 时（skill 埋在子目录里）必须加 --full-depth，
# 否则会报 "no skill found"
```

`-g` 是用户级（写入 `~/.agents/skills`），不加就是当前项目。`--json` 会输出实际落盘路径，装完扫一眼确认是 `~/.agents/skills/<name>` 而不是某个 agent 的私有目录。

也接受整条 URL 或 skills.sh 页面地址，CLI 会自己解析。

## 手动搬迁（从私有目录搬到公共目录）

顺序不能乱，尤其是第 3 步——**漏掉它 skill 会静默失效**，因为里面写死了旧路径。

1. **先查冲突**：目标目录已有同名 skill 就先停手，问清楚要保留哪份。
2. **`mv` 整个目录**，不要 `cp`。留一份在旧位置 = 两份同名 skill 被同时加载。
3. **改掉所有硬编码路径**：
   ```bash
   cd ~/.agents/skills && grep -rn -E '\.config/opencode/skills|\.pi/agent/skills|\.claude/skills' --exclude-dir=node_modules .
   ```
   命中的 `~/.config/opencode/skills/foo/scripts/x.sh` 要改成 `~/.agents/skills/foo/scripts/x.sh`。注意 SKILL.md 里的示例命令、脚本里的默认路径、README 都要看；README 里讲"上游怎么装"的可以留着不动。
4. **删掉旧位置的软链**。`~/.pi/agent/skills/skill-creator -> ~/.agents/skills/skill-creator` 这种补链在 pi 原生读取之后就是重复加载。
5. **复查**：第 3 步的 grep 必须零输出。

`scripts/audit.sh` 可以一次做完第 1、5 步和全局去重。

## 审计

```bash
bash ~/.agents/skills/skill-manager/scripts/audit.sh
```

输出：每处 skill 的 名字 / 路径 / 是实体目录还是软链 / 是否指向已失效目标，末尾列出跨目录重名和空目录。搬迁前后各跑一次，diff 一下就知道有没有漏。

## 验证

静态检查不够，要跑真的。

```bash
# A. CLI 视角：确认都归在 ~/.agents/skills 下
npx skills list

# B. pi 视角：真跑一次，让它报出能看到的 skill 名
pi -p --no-session "只回答一行：你能看到哪些 skill 的名字？用逗号分隔，不要解释。"

# C. opencode：会话内通常热加载，新加/搬动的 skill 会立刻出现在可用列表里；
#    没出现就重开一个会话
```

B 是最硬的证据——它走的是 pi 真实的 system prompt 组装路径，不是读配置文件。搬迁后建议都跑一遍，确认预期数量对得上。

## 维护

```bash
npx skills update            # 更新所有已登记的
npx skills update <name>     # 只更新一个
npx skills remove <name> -g  # 卸载（从 ~/.agents/skills 删除）
```

`~/.agents/.skill-lock.json` 记录着"通过 CLI 装过哪些、来自哪个仓库"。手动 `mv` 进去的 skill 不在里面，显示为 `untracked`，不影响使用，但 `npx skills update` 也管不到它们——这类 skill 只能靠 git 或 chezmoi 自己同步。

详见 `references/pitfalls.md`（体积、软链、dotfiles、同名冲突的具体处理）。

## 四类常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 装完 A 能用、B 不能 | 装进了 A 的私有目录 | 按上面"手动搬迁"搬到 `~/.agents/skills` |
| skill 列表里出现两次同名 | 公共目录有一份，某个私有目录还留着软链或副本 | `audit.sh` 找出第二处删掉 |
| 触发了但脚本报 `No such file` | SKILL.md 里写死了旧的绝对路径 | 第 3 步 grep 改掉 |
| 新机器上 skill 全没了 | `~/.agents/skills` 没纳入 dotfiles | `chezmoi add ~/.agents/skills` 或把该目录提交到自己的 dotfiles 仓库 |
