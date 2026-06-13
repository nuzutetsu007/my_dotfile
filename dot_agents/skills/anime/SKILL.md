---
name: anime
description: >
  动画资源管理 Skill。用户提供动画名称、别名、自然语言描述或截图，
  Skill 自动完成动画识别、资源搜索、资源选择、下载、整理和媒体库集成。
  触发条件：用户提到下载/追番/补番/识别动画/截图识别/某部动画名字，
  或涉及动画资源获取、整理、管理的任何请求。
  即使只是简单说"下载XX"或"帮我追XX"，也要使用本 Skill。
  不依赖 RSS、Sonarr、Prowlarr、qBittorrent、Shoko 等外部工具。
---

# Anime Skill — 动画资源管理

## 核心原则

- **Agent First**: 用户只表达"想看什么"，不接触技术细节
- **No External Dependencies**: 不依赖 RSS/Sonarr/Prowlarr/qBittorrent/Shoko/Jellyfin/Plex/Emby
- **Single Binary Download**: 使用 rqbit (v8.1.1) 处理所有 BitTorrent 下载
- **Memory Driven**: 持续学习用户偏好，自动优化资源选择
- **Bangumi Primary**: 使用 Bangumi API 作为动画元数据权威来源
- **User Confirmation**: 关键决策点必须向用户确认

## 工作流概览

```
用户输入 → 动画识别 → 元数据获取 → 资源搜索
  → 资源选择 → 路径确认 → 下载 → 整理 → 报告
```

---

## 1. 动画识别

### 输入类型

用户可能通过以下方式指定动画:

| 输入类型 | 示例 |
|---------|------|
| 中文名称 | "下载葬送的芙莉莲" |
| 日文名称 | "葬送のフリーレン" |
| 英文名称 | "Frieren: Beyond Journey's End" |
| 别名 | "芙莉莲"、"芙芙" |
| 自然语言 | "那个关于精灵法师活了很久的动画" |
| 截图 | 用户提供图片文件，需要识别画面内容 |
| 季度信息 | "2024年10月新番那个" |

### 识别策略

1. **名称搜索**: 使用 Bangumi API 搜索 (`https://api.bangumi.tv/search/subject/{keyword}`)
2. **截图识别**: 用户上传图片时，先用视觉能力描述画面特征，再结合 Bangumi 搜索
3. **模糊匹配**: 支持拼音、常见错别字、缩写
4. **多轮确认**: 模糊匹配命中多个结果时，列出给用户选择

### API 调用

```bash
# Bangumi 搜索
curl -s "https://api.bgm.tv/search/subject/葬送的芙莉莲?type=2" | jq .

# Bangumi 详情
curl -s "https://api.bgm.tv/subject/{subject_id}" | jq .
```

`type=2` 表示只搜索 anime 类型。

### 识别确认模板

找到疑似目标后，向用户展示确认信息：

```
🎯 识別到动画:
   名称: {name_cn} / {name_jp}
   放送状态: {status} (已放送{eps_count}话)
   季度: {season} | 总集数: {total_eps}
   Bangumi: https://bgm.tv/subject/{subject_id}

  ✓ 确认正确? (y/N)
  ❌ 或输入正确名称:
```

---

## 2. 元数据获取

动画确认后，获取以下元数据并建立统一标识:

- **Bangumi Subject ID**: 主键标识
- **正式中文名**: `name_cn`
- **正式日文名**: `name_jp`
- **正式英文名**: 通过别名列表提取
- **放送状态**: `airing` / `finished` / `not_yet_aired`
- **季度信息**: 放送季度 (如 `2024-秋`)
- **总集数**: `total_episodes`
- **当前已放送**: `airing_episodes` (放送中适用)
- **各话标题/放送日**: 用于后续剧集识别
- **封面图**: URL 备用

存储为 JSON 用于后续工作流:

```json
{
  "id": "bangumi:{subject_id}",
  "title_cn": "葬送的芙莉莲",
  "title_jp": "葬送のフリーレン",
  "title_en": "Frieren: Beyond Journey's End",
  "aliases": ["芙莉莲", "芙芙", "Frieren"],
  "status": "finished",
  "season": "2023-秋",
  "total_episodes": 28,
  "airing_episodes": 28,
  "bangumi_url": "https://bgm.tv/subject/420723",
  "cover_url": "https://lain.bgm.tv/pic/cover/l/..."
}
```

---

## 3. 资源发现

### 搜索策略

主动搜索资源来源（不依赖 RSS Push），支持的来源:

| 来源 | 类型 | 说明 |
|------|------|------|
| Mikan Project | Torrent/Magnet | 主要来源，中文资源最全 |
| Nyaa.si | Torrent/Magnet | 主要来源，英文/日文/多语资源 |
| Bangumi | 关联资源 | Bangumi 关联的资源页 |

### 搜索方法

**Mikan Project 搜索**:
```
https://mikan.tangbai.cc/Home/Search?searchstr={keyword}
```
爬取结果页，提取标题、大小、Magnet、日期。Mikan 不显示种子数。

**Nyaa.si 搜索**:
```
https://nyaa.si/?q={keyword}&f=0&c=1_0
```
爬取结果页，提取标题、大小、种子数、做种数、Torrent/Magnet 链接。

### 资源聚合

将多来源结果聚合为统一结构:

```json
{
  "resources": [
    {
      "source": "mikan",
      "title": "[ANi] 葬送的芙莉莲 - 01 [1080P][Baha][WEB-DL][AAC AVC][CHT]",
      "size": "512MB",
      "seeders": 45,
      "leechers": 12,
      "magnet": "magnet:?xt=urn:btih:...",
      "torrent_url": "https://...",
      "metadata": {
        "sub_group": "ANi",
        "episode": 1,
        "resolution": "1080P",
        "codec": "AVC",
        "audio": "AAC",
        "subtitle_lang": "CHT",
        "is_collection": false
      }
    }
  ]
}
```

**重要**: 解析资源标题时，提取:
- 字幕组 (Sub group)
- 剧集编号 (Episode number)
- 分辨率 (Resolution)
- 视频编码 (Codec: AVC/HEVC/x264/x265)
- 音频格式 (Audio: AAC/FLAC/Opus)
- 字幕语言 (Subtitle: CHT/CHS/CHS&CHT/ENG)
- 是否合集/收藏版 (Collection flag)

---

## 4. 资源选择

### 历史偏好学习

使用 `memory_search` 和 `memory_save` 记录用户偏好:

```json
{
  "type": "anime_preference",
  "content": {
    "preferred_sub_groups": ["ANi", "VCB-Studio", "LoliHouse"],
    "preferred_codecs": ["HEVC", "x265"],
    "preferred_subtitle_langs": ["CHS&CHT", "CHS"],
    "prefer_collection": true,
    "prefer_smaller_size": false,
    "downloaded_anime": ["bangumi:420723", "bangumi:123456"]
  }
}
```

每次用户选择手动覆盖时，保存这次选择到 memory。

### 自动排序算法

资源得分 = 各维度加权和:

| 维度 | 权重 | 规则 |
|------|------|------|
| 字幕组匹配 | 0.25 | 匹配偏好 +0.25, 有知名度但无偏好 +0.15 |
| 编码格式 | 0.20 | HEVC/x265 +0.20, AVC +0.10 |
| 字幕语言 | 0.20 | 优先匹配偏好语言 |
| 资源健康度 | 0.20 | 基于 (seeders / (seeders + leechers + 1)) * 0.20 |
| 非合集加分 | 0.10 | 单集下载优先选单集资源 |
| 合集加分 | 0.05 | 补番/全集下载合集资源加分 |
| 体积大小 | 0～-0.10 | prefer_smaller_size 时, 体积越小越高分 |

### 选择流程

1. 加载用户偏好 (memory_search)
2. 对每个资源计算得分
3. 按得分降序排列
4. 取 Top-1 推荐给用户，同时列出 Top-3 备选
5. 用户可确认首选或选择备选
6. 用户选择覆盖时，记录到 memory

### 展示模板

```
📊 已搜索到 {count} 个资源，按偏好排序如下:

  [1] ★ {sub_group} - {episode}话 [{resolution} {codec} {audio}]
      大小: {size} | 做种: {seeders}人 | 字幕: {subtitle_lang}
      Magnet: {magnet_short}

  [2] {sub_group} - {episode}话 ...
  [3] ...

  ✓ 选择 [1] (默认回车)
  ❌ 或输入编号选择其他资源:
```

---

## 5. 下载

### rqbit 配置

使用 rqbit 下载。首次使用或更新运行 `scripts/install_rqbit.sh` (自动检测最新版, 失败回退 v8.1.1)。

### 下载位置确认

**每次用户发起下载任务时，必须询问用户下载位置:**


```
📂 下载到哪里?
   > (输入路径，如 /mnt/media/Anime)
   > 回车使用默认: {suggested_path}
```

**建议默认路径策略:**
- 优先使用用户上次使用的路径（从 memory 读取 `last_download_path`）
- 无历史记录则提议 `~/Downloads/anime/{anime_name}/`
- 用户选择后保存到 memory

### 下载命令

```bash
# 单集下载
rqbit download -o "{output_dir}" -e --overwrite "{magnet_url}"

# 指定文件名过滤（如需只下特定文件）
rqbit download -o "{output_dir}" -r ".*{episode_padded}.*" -e --overwrite "{magnet_url}"

# 查看种子内容（列出文件列表）
rqbit download -o /tmp/rqbit-list -l "{magnet_url}"
```

关键参数:
- `-o {output_dir}`: 输出目录
- `-e`: 下载完成后退出 (--exit-on-finish)
- `--overwrite`: 覆盖已有文件
- `-l`: 仅列出种子内容
- `-r "{regex}"`: 文件名过滤正则

### 下载队列

并发下载控制在 2-3 个任务同时进行。使用 bash 后台作业管理:

```bash
# 后台启动下载
rqbit download -o "{dir}" -e --overwrite "{magnet}" > "{log_file}" 2>&1 &
PID=$!
echo $PID >> /tmp/rqbit-pids-{anime_id}.txt

# 等待下载完成
wait $PID

# 清理
rm -f /tmp/rqbit-pids-{anime_id}.txt
```

### 下载后校验

rqbit 自动进行 BitTorrent 数据校验，下载完成后检查:
1. 文件存在性: `ls -la "{output_dir}/"`
2. 文件大小合理性: 文件非空且大小 > 1MB
3. 失败处理: 重试 1 次，仍失败则通知用户

---

## 6. 文件整理

### 识别剧集编号

从资源标题和种子内文件名，通过正则提取剧集编号:

```
# 常见格式
EP01, ep01, 第01话, 第01集, 01v2, 01 (TV), 01 (BD)
# 特殊格式
SP01, OVA, Movie, NCED, NCOP
```

### 标准目录结构

```
{base_dir}/
└── {anime_cn_name}/
    ├── Season 1/
    │   ├── {anime_cn_name} - S01E01 - {ep_title}.mkv
    │   ├── {anime_cn_name} - S01E02 - {ep_title}.mkv
    │   └── ...
    ├── Specials/
    │   ├── {anime_cn_name} - SP01.mkv
    │   └── ...
    └── .meta/
        ├── bangumi.json          # 动画元数据
        ├── source_info.json      # 资源来源信息
        └── download_history.json # 下载历史
```

### 文件命名规范

```
{动画正式中文名} - S{季数}E{集数} - {各话标题}.{ext}
{动画正式中文名} - SP{特殊编号}.{ext}
```

### 保留元数据

在 `.meta/` 目录保存:
- `bangumi.json`: 第2步获取的完整元数据
- `source_info.json`:
  ```json
  {
    "resource_title": "[ANi] ...",
    "sub_group": "ANi",
    "source_url": "https://mikan.tangbai.cc/...",
    "source_type": "mikan",
    "resolution": "1080P",
    "codec": "AVC",
    "subtitle_lang": "CHT",
    "magnet": "magnet:?...",
    "download_time": "2025-01-15T10:30:00Z"
  }
  ```
- `download_history.json`: 每次下载追加记录

---

## 7. 流程图（决策参考）

```
User Input
  │
  ▼
┌─────────────────────────────┐
│  Anime Recognition          │
│  (Bangumi API Search)       │
└────────┬────────────────────┘
         │
    ┌────▼────┐
    │ Confirm │──No──→ User corrects → Re-search
    └────┬────┘
         │ Yes
         ▼
┌─────────────────────────────┐
│  Get Full Metadata          │
│  (episodes, season, status) │
└────────┬────────────────────┘
         ▼
    ┌──────────┐
    │ 追番？   │──Yes──→ Identify next undownloaded episode
    │ 补番？   │──Yes──→ Identify all episodes
    │ 单集？   │──Yes──→ Target specific episode
    └──────────┘
         │
         ▼
┌─────────────────────────────┐
│  Search Resources           │
│  (mikan + nyaa)              │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│  Score & Rank Resources     │
│  (preference + health)      │
└────────┬────────────────────┘
         ▼
    ┌──────────┐
    │ Show Top │──User selects or manual override──→ Save to memory
    └──────────┘
         │
         ▼
┌─────────────────────────────┐
│  Ask Download Location      │
│  (use memory or user input) │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│  Download via rqbit         │
│  (concurrent queue, 2-3)    │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│  Verify files               │
│  (size check, non-empty)    │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│  Organize & Rename          │
│  (standard dir structure)   │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│  Save .meta/ metadata       │
└────────┬────────────────────┘
         ▼
    Report completion to user
```

---

## 8. 特殊情况处理

### 放送中动画（追番）

1. 识别当前已放送但未下载的剧集
2. 搜索最新话资源
3. 下载最新话
4. 记录进度到 memory，下次可继续
5. 询问用户是否需要一次性下载所有已放送话数

### 已完结动画（补番）

1. 搜索合集资源（优先）
2. 合集资源不可用 -> 逐集搜索下载
3. 自动检测缺失集数并补全

### 多季度动画

1. 通过 Bangumi 识别各季度关系
2. 按 Season 1 / Season 2 组织目录
3. 用户可指定下载特定季度

### 截图识别

1. 用户提供截图 -> 读取图片文件
2. 用视觉能力描述画面（角色特征、背景风格、色调、文字）
3. 结合描述搜索 Bangumi
4. 列出 Top-3 备选动画让用户确认

### OVA / Movie / Special

1. 从 Bangumi 元数据识别类型
2. 归入 Specials 目录
3. 命名带上类型标识

### 多语言字幕

1. 用户偏好语言决定优先级
2. 字幕语言标注: CHS (简体), CHT (繁體), CHS&CHT (简繁), ENG (英文)
3. 无匹配时降级到最接近选项

---

## 9. Memory 接口

### 保存偏好

```javascript
// 用户手动选择覆盖时
memory_save({
  type: "anime_preference",
  content: {
    preferred_sub_groups: [...],
    preferred_codecs: [...],
    preferred_subtitle_langs: [...],
    prefer_collection: true/false,
    prefer_smaller_size: true/false
  }
})

// 记录下载路径
memory_save({
  type: "anime_download_path",
  content: {
    path: "/mnt/media/Anime",
    last_used: "2025-01-15T10:30:00Z"
  }
})

// 记录追番进度
memory_save({
  type: "anime_progress",
  content: {
    bangumi_id: "420723",
    title: "葬送的芙莉莲",
    season: 1,
    last_downloaded_episode: 10,
    total_downloaded_episodes: [1,2,3,4,5,6,7,8,9,10],
    status: "watching"
  }
})
```

### 读取偏好

```javascript
memory_search({ query: "anime_preference" })
memory_search({ query: "anime_download_path" })
memory_search({ query: "anime_progress 葬送" })
```

---

## 10. 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| Bangumi 搜索无结果 | 提示用户改名称，建议中日英任选 |
| 资源来源无搜索结果 | 告知用户该动画暂无可用资源 |
| 所有资源做种数=0 | 警告用户可能需要等待，是否继续下载 |
| 下载失败 | 自动重试 1 次，仍失败则报错 |
| rqbit 未安装 | 参考 `references/rqbit.md` 下载安装 |
| 目录权限不足 | 提示用户使用 sudo 或选择其他路径 |
| 磁盘空间不足 | 检查空间，提前警告并建议更换路径 |

---

## 11. 媒体库集成（可选）

默认仅整理文件到目录。媒体服务器支持通过插件扩展:

- **Jellyfin**: 整理后 Jellyfin 自动扫描标准目录结构即可识别
- **Plex**: 同上
- **Emby**: 同上
- **Webhook**: 下载完成可触发回调
- **Discord/Telegram**: 通知推送（待实现）

标准目录结构兼容主流媒体服务器刮削规则。

---

## 12. 用户交互体验

### 简洁状态报告

每个步骤用单行 emoji + 简短描述：

```
🔍 识别动画: 葬送的芙莉莲
✅ Bangumi 确认: 2023-秋 | 全28话
🔎 搜索资源... 找到 15 个资源
📊 最佳推荐: ANi - 1080P HEVC CHT (45做种)
📂 下载位置: /mnt/media/Anime/葬送的芙莉莲/
⬇️  下载中... 集数 [01/28]
✅ 下载完成: 01 - 旅立ちの絆
📁 文件整理完成
✅ 全部完成! 共下载 28 集
```

### 常见用户请求映射

| 用户说 | Action |
|--------|--------|
| "下载/看/追 {name}" | 识别 → 确认 → 搜索 → 选资源 → 下载 |
| "最新一集 {name}" | 识别 → 查最新话 → 搜索该话 → 下载 |
| "补完/全集 {name}" | 识别 → 全集搜索 → 合集优先 → 逐集补缺 |
| "识别这张截图" | 读图 → 视觉描述 → 搜索 → Top-3 确认 |
| "{name}更新了吗" | 识别 → 查状态 → 返回最新话信息 |