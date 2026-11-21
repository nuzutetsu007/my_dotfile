---
name: epub2anki
description: |
  从英文 EPUB 生成 Anki 词汇牌组 (.apkg) 的完整 pipeline。
  任何时候用户提到 epub 转 Anki、制作词汇卡片、从书里提取单词做牌组、批量制卡、或涉及 autoanki 项目,
  都使用本 Skill。
  本 Skill 处理完整流程: 解析 EPUB → 滑动窗口分片 → LLM 推理提取 GRE/六级词汇 → 打包 .apkg。
  支持断点续跑、分片范围调试、快速预览提取结果。
compatibility:
  tools: [read, write, edit, bash]
  dependencies: [uv, markitdown, genanki]
---

# epub2anki — EPUB 转 Anki 词汇牌组

从英文 EPUB 书提取 GRE/六级/考研词汇, 生成 Anki .apkg 文件。全部本地推理 (llama.cpp server), 无 API 费用。

## 前置条件

- Python ≥ 3.13, `uv` 包管理器
- `markitdown` (cli) — 用于 EPUB→Markdown 导出
- `llama.cpp server` 运行在 `http://127.0.0.1:8080` 提供 LLM 推理
- `genanki` — Anki 牌组打包

项目通常位于 `autoanki/` 目录, 结构:

```
autoanki/
├── autoanki/
│   ├── pipeline.py    # 4 阶段流水线函数
│   └── cli.py         # typer CLI 入口
├── ass/               # 原始素材 (EPUB 放这里)
├── _run_state/        # 断点状态 (自动创建)
└── pyproject.toml
```

## 工作流程

### 1. 初始化项目

如果用户没有 `autoanki/` 项目, 先创建。复制 `pipeline.py` 和 `cli.py` 模板。

关键配置在 `autoanki/pipeline.py` 顶部 Config 区:

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ASS_DIR` | `Path("ass")` | 素材目录 |
| `MD_FILE` | `ASS_DIR / "xxx.md"` | markitdown 导出目标 |
| `EPUB_FILE` | `ASS_DIR / "xxx.epub"` | 输入 EPUB |
| `OUTPUT_APKG` | `"xxx.apkg"` | 输出文件 |
| `API_URL` | `"http://127.0.0.1:8080/v1/chat/completions"` | LLM 服务地址 |
| `MODEL_NAME` | `"unsloth/gemma-..."` | LLM 模型名 |
| `CHUNK_SIZE` | 2000 | 滑动窗口字符数 |
| `MODEL_ID` / `DECK_ID` | 随机的整数 | Anki model/deck ID, 每次换书改 |

**必须修改的变量 (每本书不同):**
- `EPUB_FILE` — 指向用户提供的 EPUB
- `MD_FILE` — 导出后的 markdown 文件名 (最好和书同名)
- `OUTPUT_APKG` — 输出 .apkg 文件名
- `MODEL_ID`, `DECK_ID` — 新随机整数, 避免 Anki 冲突

### 2. 准备素材

1. 将 EPUB 文件放入 `ass/` 目录
2. 修改 `pipeline.py` 中 Config 区的文件路径变量

### 3. 安装依赖

```bash
cd autoanki
uv sync  # 或 uv add genanki typer
pip install markitdown  # cli 工具, 全局安装
```

### 4. 运行 Pipeline

**完整流程 (自动断点续跑):**
```bash
cd autoanki
uv run autoanki run
```

**分片快速调试 (30 秒看效果):**
```bash
uv run autoanki run --limit 3
```

**指定范围:**
```bash
uv run autoanki run --chunks 10-20
```

**只看分片, 不推理:**
```bash
uv run autoanki run --dry-run
```

**查看已提取词汇:**
```bash
uv run autoanki inspect
uv run autoanki inspect --dupes  # 只看重复词
```

### 5. 分步执行 (调试用)

```bash
uv run autoanki chunk                    # stage1+2: 分片
uv run autoanki infer                    # stage3: 推理
uv run autoanki infer --limit 5          # 只推理前 5 chunk
uv run autoanki package                  # stage4: 打包
```

### 6. 输出

- `wimpy_kid_minicpm.apkg` (配置的名称) — Anki 牌组文件
- `_run_state/results.jsonl` — 逐行追加的提取结果
- `_run_state/progress.json` — 已完成 chunk 记录 (断点用)

## 断点续跑机制

Stage 3 (推理) 每成功一个 chunk:
1. 追加写入 `_run_state/results.jsonl`
2. 更新 `_run_state/progress.json`

中断后重跑自动跳过已完成 chunk:

```bash
uv run autoanki run
# → 47 chunk, 已有 30 → 只跑 31-47
```

如需强制重跑全部:

```bash
uv run autoanki run --no-resume
```

## 架构

5 阶段流水线, 定义在 `cli.py`:

1. **Stage 1 (preprocess)** — `markitdown` 导出 EPUB→Markdown, 清洗 front matter / 图片标记 / 空行
2. **Stage 2 (chunk)** — 滑动窗口分片, 在句子边界切割, 每片 ~2000 字符
3. **Stage 3 (infer)** — 逐片请求 llama.cpp, 解析 `单词 || 原文句子 || 中文释义` 格式
4. **Stage 4 (tts)** — 可选, kitten-tts 生成单词+例句音频, 支持断点续跑
5. **Stage 5 (package)** — `genanki` 构建牌组, 每张卡片: 正面单词, 反面例句+释义+音频

## 故障排除

- **`llama.cpp` 连不上**: 确认 server 在 `http://127.0.0.1:8080` 运行
- **导出空文件**: 检查 EPUB 路径是否正确
- **分片太多/太少**: 调 `CHUNK_SIZE` 和 `CHUNK_OVERLAP`
- **提取了重复单词**: `uv run autoanki inspect --dupes` 查看