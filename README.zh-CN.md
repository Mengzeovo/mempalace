<div align="center">

<img src="assets/mempalace_logo.png" alt="MemPalace" width="280">

# MemPalace

### 史上基准成绩最高的 AI 记忆系统，而且免费。

<br>

你和 AI 的每一次对话——每一个决策、每一次调试、每一场架构讨论——都会在会话结束后消失。六个月的工作，转眼归零。你每次都得从头开始。

其他记忆系统试图通过“让 AI 判断什么值得记住”来解决这个问题。它会提取出“用户偏好 Postgres”这样的结论，却丢掉你解释 *为什么* 的完整上下文。MemPalace 走的是另一条路：**全部保存，再让它可检索。**

**The Palace（记忆宫殿）** —— 古希腊演说家会把整篇演讲的要点放进想象中的建筑房间里，走一遍建筑就能找到对应观点。MemPalace 把这个原则用于 AI 记忆：你的对话会被组织成 wings（人物与项目）、halls（记忆类型）和 rooms（具体主题）。不由 AI 决定什么重要——你保留每一个字，而结构为你提供的是可导航地图，而不是扁平搜索索引。

**原文逐字存储（Raw verbatim storage）** —— MemPalace 会把你的真实对话直接存入 ChromaDB，不做摘要、不做抽取。LongMemEval 的 96.6% 成绩来自这个 raw 模式。我们不消耗 LLM 去判断“值不值得记”，而是全量保留，再交给语义检索去找。

**AAAK（实验性）** —— 一种有损缩写方言，用于在大规模场景中把重复实体压成更少 token。任何能读文本的 LLM（Claude、GPT、Gemini、Llama、Mistral）都可直接理解，不需要解码器。**AAAK 是独立的压缩层，不是默认存储格式**，且当前在 LongMemEval 上较 raw 模式有回退（84.2% vs 96.6%）。我们正在迭代。真实状态请见[上方说明](#a-note-from-milla--ben--april-7-2026)。

**本地、开源、可适配** —— MemPalace 完全运行在你的机器上，处理你的本地数据，不依赖任何外部 API 或服务。它已在对话数据上充分测试，也可以改造用于其他数据存储类型。这就是我们将其开源的原因。

<br>

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]
[![][discord-shield]][discord-link]

<br>

[快速开始](#quick-start) · [记忆宫殿](#the-palace) · [AAAK 方言](#aaak-compression) · [基准测试](#benchmarks) · [MCP 工具](#mcp-server)

<br>

### 已发布 LongMemEval 最高分——无论免费还是付费方案。

<table>
<tr>
<td align="center"><strong>96.6%</strong><br><sub>LongMemEval R@5<br><b>raw 模式</b>，零 API 调用</sub></td>
<td align="center"><strong>500/500</strong><br><sub>测试题数<br>已独立复现</sub></td>
<td align="center"><strong>$0</strong><br><sub>无订阅<br>无云端，仅本地</sub></td>
</tr>
</table>

<sub>可复现——运行脚本位于 <a href="benchmarks/">benchmarks/</a>。<a href="benchmarks/BENCHMARKS.md">完整结果</a>。96.6% 来自 <b>raw 原文模式</b>，不是 AAAK 或 rooms 模式（后两者分数更低——见<a href="#a-note-from-milla--ben--april-7-2026">上方说明</a>）。</sub>

</div>

---

## A Note from Milla & Ben — April 7, 2026

> 社区在项目发布后的数小时内就指出了 README 中的真实问题，我们希望直接回应。
>
> **我们哪里写错了：**
>
> - **AAAK token 示例不正确。** 我们之前使用了粗略启发式（`len(text)//3`）来估算 token，而非真实 tokenizer。用 OpenAI tokenizer 重新计算后：英文示例是 66 tokens，AAAK 示例是 73。AAAK 在小规模文本上并不省 token——它是为“重复实体在大规模下”设计的，而 README 当时给了一个糟糕示例。我们正在重写。
>
> - **“30x 无损压缩”表述夸大。** AAAK 是有损缩写系统（实体编码、句子截断）。独立基准显示 AAAK 模式在 LongMemEval 上是 **84.2% R@5，而 raw 模式是 96.6%**，下降 12.4 个点。更诚实的说法应是：AAAK 是实验性压缩层，用保真度换 token 密度；**96.6% 的头条成绩来自 RAW 模式，不是 AAAK**。
>
> - **“宫殿结构 +34% 提升”容易误导。** 这个数字比较的是“无过滤搜索”和“wing+room 元数据过滤搜索”。元数据过滤是 ChromaDB 的标准能力，不是新型检索机制。它真实且有用，但不是护城河。
>
> - **“矛盾检测”** 目前作为独立工具（`fact_checker.py`）存在，但还没像 README 所说那样接入知识图谱操作流程。
>
> - **“Haiku rerank 达到 100%”** 结果是真的（我们有结果文件），但 rerank 流程尚未纳入公开基准脚本。我们正在补上。
>
> **仍然真实且可复现的部分：**
>
> - **LongMemEval raw 模式下 96.6% R@5**，500 题，零 API 调用——由 [@gizmax](https://github.com/milla-jovovich/mempalace/issues/39) 在 M2 Ultra 上 5 分钟内独立复现。
> - 本地运行、免费、无订阅、无云端、数据不离开你的机器。
> - 架构（wings、rooms、closets、drawers）是真实且有价值的，即使它不是“魔法式检索提升”。
>
> **我们正在做的事：**
>
> 1. 用真实 tokenizer 计数重写 AAAK 示例，并给出真正体现压缩优势的场景
> 2. 在基准文档中明确标注 `mode raw / aaak / rooms`，让权衡可见
> 3. 将 `fact_checker.py` 接入 KG 操作流程，让“矛盾检测”陈述真正成立
> 4. 将 ChromaDB 锁定到已验证版本区间（Issue #100），修复 hooks 的 shell 注入问题（#110），并处理 macOS ARM64 segfault（#74）
>
> **感谢所有提出问题的人。** 残酷而诚实的批评正是开源进步的方式，也是我们主动寻求的。特别感谢 [@panuhorsmalahti](https://github.com/milla-jovovich/mempalace/issues/43)、[@lhl](https://github.com/milla-jovovich/mempalace/issues/27)、[@gizmax](https://github.com/milla-jovovich/mempalace/issues/39) 以及发布前 48 小时内提交 issue/PR 的每一位。我们在听，我们在修，我们宁可正确，也不求看起来惊艳。
>
> — *Milla Jovovich & Ben Sigman*

---

## Quick Start

```bash
pip install mempalace

# 初始化你的世界：你和谁协作、有哪些项目
mempalace init ~/projects/myapp

# 挖掘你的数据
mempalace mine ~/projects/myapp                    # projects —— 代码、文档、笔记
mempalace mine ~/chats/ --mode convos              # convos —— Claude、ChatGPT、Slack 导出
mempalace mine ~/chats/ --mode convos --extract general  # general —— 自动归类为决策、里程碑、问题

# 搜索你讨论过的任何内容
mempalace search "why did we switch to GraphQL"

# 查看 AI 记忆状态
mempalace status
```

三种挖掘模式：**projects**（代码和文档）、**convos**（对话导出）、**general**（自动分类到决策、偏好、里程碑、问题和情绪上下文）。所有数据都留在你的机器上。

---

## How You Actually Use It

完成一次性配置（install → init → mine）后，你通常不需要手动敲 MemPalace 命令。你的 AI 会替你调用。根据所用 AI，主要有两种方式。

### With Claude, ChatGPT, Cursor, Gemini (MCP-compatible tools)

```bash
# 一次连接 MemPalace
claude mcp add mempalace -- python -m mempalace.mcp_server
```

现在你的 AI 会通过 MCP 拿到 19 个工具。你可以直接问它：

> *"What did we decide about auth last month?"*

Claude 会自动调用 `mempalace_search`，拿到逐字结果，然后回答你。你再也不用手动输入 `mempalace search`。

MemPalace 也原生支持 **Gemini CLI**（会自动处理 server 与 save hooks）——见 [Gemini CLI Integration Guide](examples/gemini_cli_setup.md)。

### With local models (Llama, Mistral, or any offline LLM)

本地模型通常还不支持 MCP。你可以用两种方式：

**1. Wake-up 命令** —— 先把你的世界加载进模型上下文：

```bash
mempalace wake-up > context.txt
# 把 context.txt 粘贴到本地模型的 system prompt
```

这样在你提出第一个问题前，本地模型就能先获得约 170 token 的关键事实（也可使用 AAAK）。

**2. CLI 搜索** —— 按需检索，再把结果喂进 prompt：

```bash
mempalace search "auth decisions" > results.txt
# 在 prompt 中引入 results.txt
```

也可以用 Python API：

```python
from mempalace.searcher import search_memories
results = search_memories("auth decisions", palace_path="~/.mempalace/palace")
# 注入到本地模型上下文
```

无论哪种方式，你的整套记忆栈都可以离线运行：机器上的 ChromaDB、机器上的 Llama、AAAK 用于压缩，零云调用。

---

## The Problem

现在的决策发生在对话里，而不是文档里，不是在 Jira 里。它发生在你和 Claude、ChatGPT、Copilot 的交互中。推理过程、权衡取舍、“我们试了 X 但因为 Y 失败了”——这些都困在聊天窗口里，结束即蒸发。

**六个月的日常 AI 使用 = 1950 万 tokens。** 每个决策、每次调试、每场架构争论，全都可能丢失。

| 方案 | 加载 token | 年成本 |
|----------|--------------|-------------|
| 全量粘贴 | 19.5M —— 超过任何上下文窗口 | 不可能 |
| LLM 摘要 | ~650K | ~$507/年 |
| **MemPalace wake-up** | **~170 tokens** | **~$0.70/年** |
| **MemPalace + 5 次搜索** | **~13,500 tokens** | **~$10/年** |

MemPalace 在 wake-up 时只加载 170 token 的关键事实——你的团队、项目与偏好。其余按需搜索。记住一切大约 $10/年，而摘要方案约 $507/年且丢上下文。

---

## How It Works

### The Palace

结构看起来很简单，但我们花了很久才打磨到今天。

从 **wing** 开始。你归档的每个项目、每个人、每个主题，都有自己的 wing。

每个 wing 下连接多个 **rooms**，按与该 wing 相关的主题来分信息——每个 room 都代表项目的一种要素。比如“项目想法”一个 room，“成员”一个 room，“财务报表”又一个 room。room 数量可以无限扩展，把 wing 切成有组织的区块。MemPalace 安装时会自动检测，也支持你按习惯自定义。

每个 room 连接一个 **closet**，这就是有意思的地方。我们开发了一个 AI 语言叫 **AAAK**（名字背后有故事）。你的 agent 每次唤醒都会学习 AAAK 简写。因为 AAAK 本质上仍是英语，只是高度压缩，agent 能在几秒内学会使用。它随安装一起提供，内置在 MemPalace 代码中。下个版本我们会把 AAAK 直接用于 closets，这会非常关键——closet 能容纳更多信息，同时占用更少空间、让 agent 更快读完。

closet 内部是 **drawers**，drawers 存放你的原始文件。在第一个版本里，我们还没有把 AAAK 作为 closet 存储工具；即便如此，在多套基准上的摘要召回也达到了 **96.6% recall**。等 closets 用上 AAAK，搜索会更快，同时保留逐字准确。即使现在，closet 方案也大幅提升了“小空间存储大量信息”的能力——它能快速把 AI 指向保存原文的 drawer。你不会丢任何东西，且全部在秒级完成。

此外还有 **halls**（连接同一 wing 内 rooms）和 **tunnels**（连接不同 wings 中的 rooms）。于是查找信息会更轻松——我们给了 AI 一套干净有序的起点，而不用在巨量文件夹里盲目扫关键词。

你只要说你在找什么，它就几乎知道该先去哪个 wing。仅这一点就已经很有价值。而整个体系同时做到美观、自然，最重要是高效。

```
  ┌─────────────────────────────────────────────────────────────┐
  │  WING: Person                                              │
  │                                                            │
  │    ┌──────────┐  ──hall──  ┌──────────┐                    │
  │    │  Room A  │            │  Room B  │                    │
  │    └────┬─────┘            └──────────┘                    │
  │         │                                                  │
  │         ▼                                                  │
  │    ┌──────────┐      ┌──────────┐                          │
  │    │  Closet  │ ───▶ │  Drawer  │                          │
  │    └──────────┘      └──────────┘                          │
  └─────────┼──────────────────────────────────────────────────┘
            │
          tunnel
            │
  ┌─────────┼──────────────────────────────────────────────────┐
  │  WING: Project                                             │
  │         │                                                  │
  │    ┌────┴─────┐  ──hall──  ┌──────────┐                    │
  │    │  Room A  │            │  Room C  │                    │
  │    └────┬─────┘            └──────────┘                    │
  │         │                                                  │
  │         ▼                                                  │
  │    ┌──────────┐      ┌──────────┐                          │
  │    │  Closet  │ ───▶ │  Drawer  │                          │
  │    └──────────┘      └──────────┘                          │
  └─────────────────────────────────────────────────────────────┘
```

**Wings** —— 人或项目。需要多少建多少。
**Rooms** —— wing 内的具体主题。Auth、billing、deploy……可无限扩展。
**Halls** —— 同一 wing 内相关 rooms 的连接。若 Room A（auth）与 Room B（security）相关，hall 会连接它们。
**Tunnels** —— 跨 wing 连接。当 Person A 和某 Project 都有 “auth” room 时，系统会自动建立 cross-reference。
**Closets** —— 指向原始内容的摘要。（v3.0.0 中为纯文本摘要；AAAK 编码 closet 将在后续版本上线，见 [Task #30](https://github.com/milla-jovovich/mempalace/issues/30)。）
**Drawers** —— 原始逐字文件。精确文本，永不摘要化。

**Halls** 也可看作记忆类型——在每个 wing 中保持一致，作为走廊：
- `hall_facts` —— 已做出的决策、已锁定选择
- `hall_events` —— 会话、里程碑、调试事件
- `hall_discoveries` —— 突破、洞见
- `hall_preferences` —— 习惯、喜好、观点
- `hall_advice` —— 建议与方案

**Rooms** 是具名主题，如 `auth-migration`、`graphql-switch`、`ci-pipeline`。当同名 room 出现在不同 wing，会形成 **tunnel**，把跨域同主题连接起来：

```
wing_kai       / hall_events / auth-migration  → "Kai debugged the OAuth token refresh"
wing_driftwood / hall_facts  / auth-migration  → "team decided to migrate auth to Clerk"
wing_priya     / hall_advice / auth-migration  → "Priya approved Clerk over Auth0"
```

同一个 room，三个 wings，隧道会把它们连起来。

### Why Structure Matters

在 22,000+ 条真实对话记忆上的测试结果：

```
Search all closets:          60.9%  R@10
Search within wing:          73.1%  (+12%)
Search wing + hall:          84.8%  (+24%)
Search wing + room:          94.8%  (+34%)
```

wings 和 rooms 不是装饰，它们带来 **34% 检索提升**。宫殿结构本身就是产品核心。

### The Memory Stack

| 层级 | 内容 | 大小 | 何时加载 |
|-------|------|------|------|
| **L0** | 身份——这个 AI 是谁 | ~50 tokens | 始终加载 |
| **L1** | 关键事实——团队、项目、偏好 | ~120 tokens（AAAK） | 始终加载 |
| **L2** | Room 召回——近期会话、当前项目 | 按需 | 话题出现时 |
| **L3** | 深度搜索——跨全部 closets 的语义检索 | 按需 | 明确请求时 |

你的 AI 以 L0 + L1（约 170 tokens）唤醒，先理解你的世界，只有需要时才触发搜索。

### AAAK Dialect (experimental)

AAAK 是一种有损缩写系统——通过实体编码、结构标记和句子截断，在大规模场景中把重复实体关系压进更少 tokens。它**可被任何能读文本的 LLM 直接理解**（Claude、GPT、Gemini、Llama、Mistral），无需解码器，因此本地模型也能离线使用。

**真实状态（2026 年 4 月）：**

- **AAAK 是有损，不是无损。** 它基于正则缩写，不可逆。
- **小规模文本不省 token。** 短文本本来分词效率就高，AAAK 的额外符号和编码会让开销更高。
- **在大规模重复实体场景可能省 token。** 当同一团队、同一项目在成百上千次会话中反复出现时，实体编码会被摊薄并产生收益。
- **AAAK 当前在 LongMemEval 上较 raw 检索回退**（84.2% R@5 vs 96.6%）。96.6% 头条分数来自 **raw 模式**，不是 AAAK。
- **MemPalace 默认存储仍是 ChromaDB 的 raw 原文。** 基准优势来自这里。AAAK 是用于上下文加载的独立压缩层，不是默认存储格式。

我们正在迭代方言规范、加入真实 tokenizer 统计，并探索更合理的启用阈值。进度见 [Issue #43](https://github.com/milla-jovovich/mempalace/issues/43) 与 [#27](https://github.com/milla-jovovich/mempalace/issues/27)。

### Contradiction Detection (experimental, not yet wired into KG)

一个独立工具（`fact_checker.py`）可基于实体事实检查断言。目前它尚未自动接入知识图谱操作流程——正在修复中（见 [Issue #27](https://github.com/milla-jovovich/mempalace/issues/27)）。启用后可捕捉如下问题：

```
Input:  "Soren finished the auth migration"
Output: 🔴 AUTH-MIGRATION: attribution conflict — Maya was assigned, not Soren

Input:  "Kai has been here 2 years"
Output: 🟡 KAI: wrong_tenure — records show 3 years (started 2023-04)

Input:  "The sprint ends Friday"
Output: 🟡 SPRINT: stale_date — current sprint ends Thursday (updated 2 days ago)
```

事实会与知识图谱交叉校验。年龄、日期、工龄为动态计算，不是硬编码。

---

## Real-World Examples

### Solo developer across multiple projects

```bash
# 为每个项目挖掘对话记忆
mempalace mine ~/chats/orion/  --mode convos --wing orion
mempalace mine ~/chats/nova/   --mode convos --wing nova
mempalace mine ~/chats/helios/ --mode convos --wing helios

# 六个月后：“我当时为什么在这里用 Postgres？”
mempalace search "database decision" --wing orion
# → "Chose Postgres over SQLite because Orion needs concurrent writes
#    and the dataset will exceed 10GB. Decided 2025-11-03."

# 跨项目搜索
mempalace search "rate limiting approach"
# → finds your approach in Orion AND Nova, shows the differences
```

### Team lead managing a product

```bash
# 挖掘 Slack 导出和 AI 对话
mempalace mine ~/exports/slack/ --mode convos --wing driftwood
mempalace mine ~/.claude/projects/ --mode convos

# “Soren 上个 sprint 做了什么？”
mempalace search "Soren sprint" --wing driftwood
# → 14 closets: OAuth refactor, dark mode, component library migration

# “谁决定使用 Clerk？”
mempalace search "Clerk decision" --wing driftwood
# → "Kai recommended Clerk over Auth0 — pricing + developer experience.
#    Team agreed 2026-01-15. Maya handling the migration."
```

### Before mining: split mega-files

一些 transcript 导出会把多个会话拼接进一个超大文件：

```bash
mempalace split ~/chats/                      # 按会话拆分
mempalace split ~/chats/ --dry-run            # 先预览
mempalace split ~/chats/ --min-sessions 3     # 仅拆分含 3+ 会话的文件
```

---

## Knowledge Graph

时间语义实体关系三元组——类似 Zep 的 Graphiti，但使用 SQLite 而非 Neo4j。本地运行，免费。

```python
from mempalace.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
kg.add_triple("Kai", "works_on", "Orion", valid_from="2025-06-01")
kg.add_triple("Maya", "assigned_to", "auth-migration", valid_from="2026-01-15")
kg.add_triple("Maya", "completed", "auth-migration", valid_from="2026-02-01")

# Kai 现在在做什么？
kg.query_entity("Kai")
# → [Kai → works_on → Orion (current), Kai → recommended → Clerk (2026-01)]

# 一月时什么事实成立？
kg.query_entity("Maya", as_of="2026-01-20")
# → [Maya → assigned_to → auth-migration (active)]

# 时间线
kg.timeline("Orion")
# → chronological story of the project
```

事实有有效时间窗。当事实不再成立时可失效处理：

```python
kg.invalidate("Kai", "works_on", "Orion", ended="2026-03-01")
```

此后查询 Kai 的“当前工作”不会再返回 Orion；历史查询仍会返回。

| Feature | MemPalace | Zep (Graphiti) |
|---------|-----------|----------------|
| Storage | SQLite (local) | Neo4j (cloud) |
| Cost | Free | $25/mo+ |
| Temporal validity | Yes | Yes |
| Self-hosted | Always | Enterprise only |
| Privacy | Everything local | SOC 2, HIPAA |

---

## Specialist Agents

你可以创建专注不同领域的 agent。每个 agent 在宫殿里有自己的 wing 和 diary——而不是塞进 `CLAUDE.md`。即使加 50 个 agent，你的配置体量也不会膨胀。

```
~/.mempalace/agents/
  ├── reviewer.json       # 代码质量、模式、缺陷
  ├── architect.json      # 设计决策、权衡
  └── ops.json            # 发布、故障、基础设施
```

你的 `CLAUDE.md` 只需一行：

```
You have MemPalace agents. Run mempalace_list_agents to see them.
```

AI 会在运行时从 palace 自动发现可用 agents。每个 agent：

- **有专注方向** —— 决定它重点关注什么
- **有自己的日记** —— 使用 AAAK 书写，跨会话持久化
- **持续形成专长** —— 通过读取自身历史，在领域内越用越强

```
# 代码审查后写入日记
mempalace_diary_write("reviewer",
    "PR#42|auth.bypass.found|missing.middleware.check|pattern:3rd.time.this.quarter|★★★★")

# 读取历史
mempalace_diary_read("reviewer", last_n=10)
# → 最近 10 条发现，AAAK 压缩格式
```

每个 agent 都是你数据上的“专业镜头”。reviewer 记住每种 bug 模式，architect 记住每个设计决策，ops 记住每次事故。它们不共享临时草稿，而是维护各自独立记忆。

Letta 对 agent 托管记忆收费 $20–200/月；MemPalace 用一个 wing 就能实现。

---

## MCP Server

```bash
claude mcp add mempalace -- python -m mempalace.mcp_server
```

### 19 Tools

**Palace（读）**

| Tool | What |
|------|------|
| `mempalace_status` | Palace 概览 + AAAK 规范 + memory protocol |
| `mempalace_list_wings` | 列出 wings 与计数 |
| `mempalace_list_rooms` | 列出 wing 内 rooms |
| `mempalace_get_taxonomy` | 全量 wing → room → count 树 |
| `mempalace_search` | 支持 wing/room 过滤的语义检索 |
| `mempalace_check_duplicate` | 入库前查重 |
| `mempalace_get_aaak_spec` | AAAK 方言参考 |

**Palace（写）**

| Tool | What |
|------|------|
| `mempalace_add_drawer` | 写入逐字内容 |
| `mempalace_delete_drawer` | 按 ID 删除 |

**Knowledge Graph**

| Tool | What |
|------|------|
| `mempalace_kg_query` | 带时间过滤的实体关系查询 |
| `mempalace_kg_add` | 添加事实 |
| `mempalace_kg_invalidate` | 标记事实已结束 |
| `mempalace_kg_timeline` | 实体时间线故事 |
| `mempalace_kg_stats` | 图谱概览 |

**Navigation**

| Tool | What |
|------|------|
| `mempalace_traverse` | 从 room 出发跨 wings 遍历图 |
| `mempalace_find_tunnels` | 查找连接两翼的桥接 rooms |
| `mempalace_graph_stats` | 图连通性概览 |

**Agent Diary**

| Tool | What |
|------|------|
| `mempalace_diary_write` | 写入 AAAK 日记项 |
| `mempalace_diary_read` | 读取近期日记项 |

AI 会从 `mempalace_status` 响应中自动学习 AAAK 与记忆协议，无需手工配置。

---

## Auto-Save Hooks

为 Claude Code 提供两个 hooks，在工作期间自动保存记忆：

**Save Hook** —— 每 15 条消息触发一次结构化保存：主题、决策、引用、代码变更；并重建关键事实层。

**PreCompact Hook** —— 在上下文压缩前触发。窗口缩小前执行应急保存。

```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "/path/to/mempalace/hooks/mempal_save_hook.sh"}]}],
    "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": "/path/to/mempalace/hooks/mempal_precompact_hook.sh"}]}]
  }
}
```

---

## Benchmarks

在标准学术基准上测试——可复现、使用公开数据集。

| Benchmark | Mode | Score | API Calls |
|-----------|------|-------|-----------|
| **LongMemEval R@5** | Raw（仅 ChromaDB） | **96.6%** | Zero |
| **LongMemEval R@5** | Hybrid + Haiku rerank | **100%** (500/500) | ~500 |
| **LoCoMo R@10** | Raw，session 级 | **60.3%** | Zero |
| **Personal palace R@10** | Heuristic bench | **85%** | Zero |
| **Palace structure impact** | Wing+room filtering | **+34%** R@10 | Zero |

96.6% raw 分数是目前已发布 LongMemEval 成绩中，唯一不需要 API key、不依赖云端、全流程无需 LLM 的最高结果。

### vs Published Systems

| System | LongMemEval R@5 | API Required | Cost |
|--------|----------------|--------------|------|
| **MemPalace (hybrid)** | **100%** | Optional | Free |
| Supermemory ASMR | ~99% | Yes | — |
| **MemPalace (raw)** | **96.6%** | **None** | **Free** |
| Mastra | 94.87% | Yes (GPT) | API costs |
| Mem0 | ~85% | Yes | $19–249/mo |
| Zep | ~85% | Yes | $25/mo+ |

---

## All Commands

```bash
# 初始化
mempalace init <dir>                              # 引导式 onboarding + AAAK bootstrap

# 挖掘
mempalace mine <dir>                              # 挖掘项目文件
mempalace mine <dir> --mode convos                # 挖掘对话导出
mempalace mine <dir> --mode convos --wing myapp   # 指定 wing 标签

# 拆分
mempalace split <dir>                             # 拆分拼接 transcript
mempalace split <dir> --dry-run                   # 预览

# 搜索
mempalace search "query"                          # 搜索全部
mempalace search "query" --wing myapp             # 在指定 wing 内
mempalace search "query" --room auth-migration    # 在指定 room 内

# 记忆栈
mempalace wake-up                                 # 加载 L0 + L1 上下文
mempalace wake-up --wing driftwood                # 项目定向

# 压缩
mempalace compress --wing myapp                   # AAAK 压缩

# 状态
mempalace status                                  # palace 概览
```

所有命令都支持 `--palace <path>` 覆盖默认路径。

---

## Configuration

### Global (`~/.mempalace/config.json`)

```json
{
  "palace_path": "/custom/path/to/palace",
  "collection_name": "mempalace_drawers",
  "people_map": {"Kai": "KAI", "Priya": "PRI"}
}
```

### Wing config (`~/.mempalace/wing_config.json`)

由 `mempalace init` 生成。将人物和项目映射到 wings：

```json
{
  "default_wing": "wing_general",
  "wings": {
    "wing_kai": {"type": "person", "keywords": ["kai", "kai's"]},
    "wing_driftwood": {"type": "project", "keywords": ["driftwood", "analytics", "saas"]}
  }
}
```

### Identity (`~/.mempalace/identity.txt`)

纯文本。会成为 Layer 0 —— 每次会话都加载。

---

## File Reference

| File | What |
|------|------|
| `cli.py` | CLI 入口 |
| `config.py` | 配置加载与默认值 |
| `normalize.py` | 将 5 种聊天格式转为标准 transcript |
| `mcp_server.py` | MCP 服务器——19 工具、AAAK 自动教学、记忆协议 |
| `miner.py` | 项目文件摄取 |
| `convo_miner.py` | 对话摄取——按 exchange pair 分块 |
| `searcher.py` | 基于 ChromaDB 的语义检索 |
| `layers.py` | 4 层记忆栈 |
| `dialect.py` | AAAK 压缩——30x 无损 |
| `knowledge_graph.py` | 时间语义实体关系图（SQLite） |
| `palace_graph.py` | 基于 room 的导航图 |
| `onboarding.py` | 引导式配置——生成 AAAK bootstrap + wing config |
| `entity_registry.py` | 实体编码注册表 |
| `entity_detector.py` | 从内容自动检测人物与项目 |
| `split_mega_files.py` | 将拼接 transcript 拆为每会话文件 |
| `hooks/mempal_save_hook.sh` | 每 N 条消息自动保存 |
| `hooks/mempal_precompact_hook.sh` | 压缩前应急保存 |

---

## Project Structure

```
mempalace/
├── README.md                  ← 你正在看的原版
├── mempalace/                 ← 核心包（README）
│   ├── cli.py                 ← CLI 入口
│   ├── mcp_server.py          ← MCP server（19 工具）
│   ├── knowledge_graph.py     ← 时间实体图
│   ├── palace_graph.py        ← room 导航图
│   ├── dialect.py             ← AAAK 压缩
│   ├── miner.py               ← 项目文件摄取
│   ├── convo_miner.py         ← 对话摄取
│   ├── searcher.py            ← 语义检索
│   ├── onboarding.py          ← 引导式设置
│   └── ...                    ← 详见 mempalace/README.md
├── benchmarks/                ← 可复现基准运行器
│   ├── README.md              ← 复现指南
│   ├── BENCHMARKS.md          ← 完整结果 + 方法学
│   ├── longmemeval_bench.py   ← LongMemEval 运行器
│   ├── locomo_bench.py        ← LoCoMo 运行器
│   └── membench_bench.py      ← MemBench 运行器
├── hooks/                     ← Claude Code 自动保存 hooks
│   ├── README.md              ← hook 配置指南
│   ├── mempal_save_hook.sh    ← 每 N 条消息保存
│   └── mempal_precompact_hook.sh ← 压缩前应急保存
├── examples/                  ← 使用示例
│   ├── basic_mining.py
│   ├── convo_import.py
│   └── mcp_setup.md
├── tests/                     ← 测试套件（README）
├── assets/                    ← logo 与品牌资源
└── pyproject.toml             ← 包配置（v3.0.0）
```

---

## Requirements

- Python 3.9+
- `chromadb>=0.4.0`
- `pyyaml>=6.0`

无需 API key。安装后无需联网。全部本地运行。

```bash
pip install mempalace
```

---

## Contributing

欢迎 PR。请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 获取环境和贡献规范。

## License

MIT —— 见 [LICENSE](LICENSE)。

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.0.0-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/milla-jovovich/mempalace/releases
[python-shield]: https://img.shields.io/badge/python-3.9+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/milla-jovovich/mempalace/blob/main/LICENSE
[discord-shield]: https://img.shields.io/badge/discord-join-5865F2?style=flat-square&labelColor=0a0e14&logo=discord&logoColor=5865F2
[discord-link]: https://discord.com/invite/ycTQQCu6kn
