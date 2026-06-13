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
- **Scripts over inline code**: 所有操作走现有脚本，不手写 ad-hoc 代码
- **Memory Driven**: 持续学习用户偏好，自动优化资源选择
- **Jikan Primary**: Jikan API (MAL) 为元数据源，AniList/Kitsu 备用
- **Nyaa First Search**: 资源搜索优先 Nyaa，Mikan 备用
- **User Confirmation**: 关键决策点必须向用户确认

## 可用脚本一览

| 脚本 | 作用 | 调用方式 |
|------|------|----------|
| `scripts/check_network.sh` | 测试各源可达性 + 自动探测代理 | `bash check_network.sh` |
| `scripts/search_nyaa.sh <keyword>` | Nyaa 搜索 → JSON | `bash search_nyaa.sh "葬送的芙莉莲"` |
| `scripts/search_mikan.sh <keyword>` | Mikan 搜索 → JSON | `bash search_mikan.sh "keyword"` |
| `scripts/parse_title.py <title>` | 解析种子标题 → 编码/集数/字幕组 | `python3 parse_title.py "[- 01 [1080p]..."` |
| `scripts/rqbit_api.py` | rqbit 统一 CLI（服务+种子+批量+查询+整理） | `python3 rqbit_api.py server start <dir>` |
| `scripts/install_rqbit.sh` | 安装/更新 rqbit | `bash install_rqbit.sh` |

## 工作流概览

```
用户输入 → check_network → 动画识别 → 元数据获取 → 资源搜索
  → 资源选择 → 路径确认 → 下载 → 整理 → 报告
```

---

## 0. 网络连通测试

**每次第一步**，运行 `bash scripts/check_network.sh`:

```
  [jikan] ✅ 200
  [nyaa]  ❌ 000  → 自动探测代理 7890 → ✅ 200(proxy:7890)
  [mikan] ❌ 000
```

**判断**:
- Jikan 必通，不通则停（无元数据源）
- Nyaa 不通时脚本自动试代理端口 7890/7891/1080/8080
- 全不通 → 告知用户开代理或切换网络

脚本输出 JSON 供后续决策:
```json
[{"source":"jikan","reachable":true,"code":"200"},
 {"source":"nyaa","reachable":false,"code":"000"}]
```

---

## 1. 动画识别

### 输入类型
中文 / 日文 / 英文名称、别名、自然语言、截图、季度信息

### 识别策略
1. **名称搜索**: Jikan API `GET https://api.jikan.moe/v4/anime?q={keyword}`
2. **截图识别**: 描述画面特征 → Jikan/AniList 搜索
3. **模糊匹配**: 拼音、常见错别字、缩写
4. **多轮确认**: 命中多个结果时列出给用户选择

### 确认模板
```
🎯 识別到动画: {title} / {title_japanese}
   MAL: https://myanimelist.net/anime/{mal_id}
   放送状态: {status} 全{episodes}话  评分: ⭐{score}
  ✓ 确认正确? (y/N)
  ❌ 或输入正确名称:
```

---

## 2. 元数据获取

通过 Jikan API 获取，AniList 补充缺失字段:

- **MAL ID**: 主键 (`mal_id`)
- **标题**: 中文/日文/英文
- **状态**: `currently_airing` / `finished_airing` / `not_yet_aired`
- **集数**: `total_episodes`
- **评分**: `score`
- **封面**: `images.jpg.large_image_url`

存储 JSON:
```json
{
  "id": "mal:52991",
  "title_cn": "葬送的芙莉莲",
  "title_jp": "葬送のフリーレン",
  "status": "finished_airing",
  "total_episodes": 28,
  "score": 9.1,
  "mal_url": "https://myanimelist.net/anime/52991"
}
```

---

## 3. 资源发现

### 搜索策略（优先级排列）

| 来源 | 方式 | 说明 |
|------|------|------|
| Nyaa.si | `scripts/search_nyaa.sh` | 全球最大动画种子站，首选 |
| Mikan | `scripts/search_mikan.sh` | 中文资源最全，Nyaa 无果时切换 |
| Anime DB API | REST API | 备用（DNS 常不通） |
| ANI-RSS API | REST API | 备用（DNS 常不通） |

**代理**: 环境变量 `HTTP_PROXY`/`HTTPS_PROXY` 全局生效

### 搜索方法

```bash
# Nyaa（首选）
http_proxy=$PROXY https_proxy=$PROXY bash scripts/search_nyaa.sh "葬送的芙莉莲"

# Mikan（备选）
http_proxy=$PROXY https_proxy=$PROXY bash scripts/search_mikan.sh "葬送的芙莉莲"
```

输出 JSON:
```json
[{"source":"nyaa","title":"[LoliHouse] ...","size":"536.2 MiB","seeders":20,"magnet":"magnet:?...","torrent_url":"https://nyaa.si/download/123.torrent"}]
```

### 标题解析

用 `scripts/parse_title.py` 解析种子标题:
```bash
python3 scripts/parse_title.py "[LoliHouse] 葬送的芙莉莲 - 01 [1080p HEVC-10bit AAC][简繁日]"
```
输出: `{"group":"LoliHouse","episode":1,"resolution":"1080p","codec":"HEVC-10bit","subtitle":"CHS&CHT&JP"}`

---

## 4. 资源选择

### 偏好学习

`memory_save({type:"anime_preference", content:{preferred_sub_groups, preferred_codecs, preferred_subtitle_langs, ...}})`

### 排序算法

| 维度 | 权重 | 规则 |
|------|------|------|
| 字幕组匹配 | 0.25 | 匹配偏好 +0.25, 知名组 +0.15 |
| 编码格式 | 0.20 | HEVC-10bit 0.25, AV1 0.22, HEVC 0.20, H264 0.10 |
| 字幕语言 | 0.20 | 优先匹配偏好语言 |
| 资源健康度 | 0.20 | seeders / (seeders+leechers+1) * 0.20 |
| 非合集/合集 | 0.10/0.05 | 单集下载优先单集，补番优先合集 |
| 体积 | 0~-0.10 | prefer_smaller_size 时越小越高 |

### 混合来源策略（全集下载）

单组未覆盖全部剧集时，采用混合方案:
```
EP01-06 LoliHouse HEVC-10bit + EP07-08 Denisplay AV1 + EP09 ToonsHub H264
```
用户确认后下载。

---

## 5. 下载

### 流程

1. **启动服务器**: `python3 scripts/rqbit_api.py server start "{output_dir}"`
2. **添加种子**: `python3 scripts/rqbit_api.py torrent add "https://nyaa.si/download/{id}.torrent"`
3. **批量添加**: `python3 scripts/rqbit_api.py batch task_list.json --output-dir "{dir}"`
4. **查询进度**: `python3 scripts/rqbit_api.py summary`
5. **全完成后整理**: 统一命名 + 写 `.meta/source_info.json`

   ```bash
   cd "{output_dir}"
   # 统一命名 名称 - S01E{ep}.ext
   for f in *.mkv; do
     ep=$(echo "$f" | grep -oP 'S01E\K\d+|[-.]\K\d{2}(?=\s*\[|\s*\))' | head -1)
     [ -n "$ep" ] && mv -v "$f" "{anime_name} - S01E$ep.mkv"
   done

   # 写来源信息
   mkdir -p .meta
   cat > .meta/source_info.json << 'EOF'
   {
     "anime": "{anime_name}",
     "files": [
       {"name": "... - S01E01.mkv", "source": "LoliHouse HEVC-10bit"},
       {"name": "... - S01E02.mkv", "source": "VARYG H264 Multi-Subs"}
     ],
     "download_time": "$(date -Iseconds)"
   }
   EOF
   ```

6. **回报用户**: 告知完成

**说明**: 用户自查进度 `python3 scripts/rqbit_api.py summary`，输出含 output_folder 路径

### task_list.json 格式
```json
{
  "tasks": [
    {"name":"EP01","type":"torrent","url":"https://nyaa.si/download/123.torrent"},
    {"name":"EP02","type":"magnet","magnet":"magnet:?xt=urn:btih:..."}
  ]
}
```

### 说明

- **优先 .torrent 文件**（含 tracker，比磁链稳）
- 磁链写入文件后 `curl -d @file` 传，避免编码问题
- 代理设 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量
- 服务器常驻后台，可复用（Web UI: `http://127.0.0.1:3030/web/`）
- 用户自查: `python3 scripts/rqbit_api.py summary`

---

## 6. 文件整理

下载完成后，统一命名并记录来源：

```bash
cd "{output_dir}"

# 统一命名
for f in *.mkv; do
  ep=$(echo "$f" | grep -oP 'S01E\K\d+|[-.]\K\d{2}(?=\s*\[|\s*\)|\s*\.)' | head -1)
  [ -n "$ep" ] && mv -v "$f" "{anime_name} - S01E$ep.mkv"
done

# 写 .meta/source_info.json
mkdir -p .meta
# (手动记录每集来源，或从下载计划读取)
```

### 标准目录结构

### 标准目录结构
```
{base_dir}/{anime_cn_name}/
├── Season 1/
│   ├── {anime_cn_name} - S01E01 - {ep_title}.mkv
│   └── ...
├── Specials/
└── .meta/
    ├── metadata.json        # 动画元数据
    ├── source_info.json     # 资源来源信息
    └── download_history.json
```

---

## 7. 流程图

```
User Input → check_network → Jikan API Search
  → Confirm → Get Metadata → 追番/补番/单集?
  → Search (Nyaa → Mikan → API)
  → Score & Rank → Show Top → User selects
  → Ask Download Location
  → rqbit server start → rqbit_api.py batch
  → Verify files → Organize → Save .meta/ → Report
```

---

## 8. 特殊情况处理

### 放送中（追番）
1. 识别已放送未下载剧集
2. 搜索最新话
3. 下载 → 记录进度到 memory
4. 询问是否一次性下载所有已放送话数

### 已完结（补番）
1. 优先合集资源
2. 合集不可用 → 逐集下载
3. 自动检测缺失集数补全

### 多季度
1. Jikan `related` 字段识别季度关系
2. Season 1 / Season 2 分目录

### OVA / Movie / Special
1. Jikan `type` 字段识别类型
2. 归入 Specials 目录

---

## 9. Memory 接口

### 保存偏好
```javascript
memory_save({type:"anime_preference", content:{preferred_sub_groups:[...], preferred_codecs:[...], preferred_subtitle_langs:[...]}})
memory_save({type:"anime_download_path", content:{path:"/mnt/media/Anime", last_used:"..."}})
memory_save({type:"anime_progress", content:{mal_id:62018, title:"一叠间漫画咖啡屋生活！", downloaded_eps:[1,2,3,4,5,6,7,8,9], source_mix:[...], status:"watching"}})
```

### 查询
```javascript
memory_search({query:"anime_preference"})
memory_search({query:"anime_download_path"})
memory_search({query:"anime_progress"})
```

---

## 10. 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| Jikan 搜索无结果 | 降级 AniList → Kitsu，仍无则提示改名 |
| Nyaa 无结果 | 切 Mikan → API 源 |
| Nyaa 不可达 | 检查 HTTP_PROXY，建议开代理 |
| 所有搜索失败 | 告知网络环境不支持 |
| 下载速度极慢 | 设代理重试 |
| 下载失败 | 自动重试 1 次 |
| rqbit 未安装 | `bash scripts/install_rqbit.sh` |
| 磁盘/权限不足 | 警告并建议更换路径 |

---

## 11. 媒体库集成（可选）

标准目录结构兼容 Jellyfin/Plex/Emby 自动刮削。下载完成后自动扫描。

---

## 12. 用户交互报告

```
🔍 识别动画: 葬送的芙莉莲
✅ MAL 确认: 2023-秋 | 全28话
🔎 search_nyaa.sh → 找到 15 个资源
📊 推荐: LoliHouse - 1080p HEVC-10bit CHS&CHT
📂 下载位置: /mnt/media/Anime/葬送的芙莉莲/
⬇️  rqbit_api.py batch → 任务已启动 (http://127.0.0.1:3030/web/)
✅ 下载完成 | 📁 整理完成 | 共 28 集
```

### 用户请求映射

| 用户说 | 动作 |
|--------|------|
| "下载/看/追 {name}" | 识别 → 确认 → 搜索 → 选资源 → 下载 |
| "最新一集 {name}" | 识别 → 查最新话 → 搜索该话 → 下载 |
| "补完/全集 {name}" | 识别 → 全集搜索 → 合集优先 → 逐集补缺 |
| "识别这张截图" | 读图 → 视觉描述 → 搜索 → Top-3 确认 |
| "{name}更新了吗" | 识别 → 查状态 → 返回最新话信息 |