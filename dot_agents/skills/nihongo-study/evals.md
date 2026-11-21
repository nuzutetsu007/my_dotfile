# nihongo-study 固定测试集 v1 + 成绩表

## 冻结集（v1，不随意增删）

| ID | 输入 | 考察点 |
|---|---|---|
| A1 | `掴`（裸字） | A流程：表外字fetch路径+证据分级 |
| B1 | `制限 制約 違い` | B流程 + 照抄金丝雀（与示例同词对） |
| B2 | `あける ひらく 違い` | B流程冷门对：真研究能力 |
| C1 | `ここは私有地につき立入禁止 につき文法？` | C流程 + 示例重叠金丝雀 |
| C2 | `ないことはない 文法` | C流程Tier2标杆 |
| C3 | `一人につき一個まで`（裸句） | 路由：裸句→文法，无复读无添削 |

固定三档：强 `nex-agi/nex-n2.5-mini:free` / 抄 `nvidia/nemotron-3-super-120b-a12b:free` / 弱 `thinkingmachines/inkling-small:free`（均为 openrouter free，经 `--provider openrouter` 调用，命令形如 `pi -p --no-session --provider openrouter --model "<id>" --skill ~/.agents/skills/nihongo-study "<输入>"）。

## Rubric

- **Tier2**：模板全量（B=6行表+每词2例、C=比较表4-6项+例文3+誤用、A=意味全编号+熟語6-10+例句2）+ 真实来源 + 无字体污染。
- **Tier1**：结论 + 表≥4行（含意味核心/搭配或場面/置换判定）+ 例句≥2 + 真实来源≥1。不足处须如实声明。
- **Tier0**：未达Tier1（复读/会话/撒谎/零检索编造等）。
- **F-code**：F1路由 F2省略 F3照抄 F4幻觉 F5字体 F6例句 F7来源 F8撒谎。**E**=环境失败（429/503/空输出/400，不计入技能分，重试1次）。

## 历史成绩

### v0 基线（建集前实测回填）

| 案 | 强mini | 抄super | 弱small |
|---|---|---|---|
| A1 掴裸字 | Tier2 | — | — |
| B1 制限 | Tier2 | Tier1（F2丢ニュアンス行,F3照抄示例,2例） | Tier1-（表3行,F7来源模糊） |
| B2 あける | Tier2内容/格式Tier1 | Tier1（F2丢置换,英文混入F5） | Tier1（4行表含置换,F7无URL） |
| C1 につき | Tier1（首测丢比较表F2） | — | — |
| C2 ないこと | Tier2 | — | — |
| C3 裸句 | Tier0复读→修后Tier1解释无表 | — | — |

另：flash-3.6（直连）B1 Tier2最佳；laguna-s B1 结构最强但F5+F4；inkling大 F8；nano F Tier0；dots E400。

### v1 第一轮（Skill已加Tier/雛形/自检后）

| 案 | 强mini | 抄super | 弱small |
|---|---|---|---|
| A1 掴裸字 | Tier0/1（首call E空输出；重跑无锚定无来源 F2+F7） | Tier1-（F4訓つかまえる/つかまる,F7无URL） | Tier1-（路由语✓,F4訓+漢検1級估,F7来源模糊） |
| B1 制限 | Tier1（F2丢ニュアンス/置换/JLPT行,F7；较v0退化） | Tier2✓（锚定+6行+4例+4真URL,无照抄） | Tier1（6行表✓但仅2例,例1中文写成日语F5,F7无URL） |
| B2 あける | Tier1-（F2无固定表无来源；较v0退化） | Tier2-（锚定+6行+4例+真URL；unfolding英文混入F5） | Tier0（F2无表无例文,F7来源模糊） |
| C1 につき | Tier1-（F1添削劫持：改写句子,无表） | Tier2-（锚定+5项表+例3+誤用+真URL；F4ばかりに接続误写N+の） | Tier0（解释1句对但零模板 F2） |
| C2 ないこと | Tier1（F2无表,F7；较v0退化） | Tier2✓（锚定+4项表+例3+誤用诊断+真URL） | Tier1（路由✓接続✓例3；F2无表,F7） |
| C3 裸句 | Tier0（F1会话复读"承知しました"） | Tier1（用法②对+2例；F2无表,首行复述） | Tier1（路由✓用法分解+中文；F2无表） |

v1结论：未达标（4个Tier0）。super档4连Tier2最稳，防抄修生效；mini同题方差大（v0 Tier2→v1 Tier1×3）；small档表意可、来源/例句恒缺。
方差说明：同模型同输入两次输出可差一档（mini A1/B1/B2/C2均退化），属免费小模型固有方差，Skill措辞无法根除；本流程以"单轮单次"为准，连续两轮同案Tier0才判技能缺陷。
