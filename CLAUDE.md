# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

### 安装
```bash
pip install -e ".[dev]"
```

### 测试
```bash
python -m pytest tests/ -v
python -m pytest tests/test_mcp_server.py -v
python -m pytest tests/test_mcp_server.py -k search -v
```

### Lint
```bash
ruff check .
```

### 打包 / 入口检查
```bash
python -m mempalace --help
python -m build
```

### 基准测试
```bash
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json --limit 20
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json
python benchmarks/locomo_bench.py /tmp/locomo/data/locomo10.json --limit 1
python benchmarks/convomem_bench.py --category user_evidence --limit 10
```

## 现有文档里的仓库约束

- 当前仓库里没有已有的 `CLAUDE.md`。
- 没有发现 `.cursor/rules/`、`.cursorrules` 或 `.github/copilot-instructions.md`。
- `CONTRIBUTING.md` 明确要求核心能力保持 local-first、默认 zero-API、以及 verbatim-first。
- PR 模板要求 `python -m pytest tests/ -v` 和 `ruff check .` 通过。

## 高层架构

MemPalace 围绕同一套本地数据模型，提供两个主要入口：

1. **CLI 的写入与检索入口**（`mempalace/cli.py`）
2. **给 AI Agent 使用的 MCP 工具服务**（`mempalace/mcp_server.py`）

这两个入口又共同建立在两层存储之上：

- **ChromaDB**：保存原文分块，也就是 palace / `mempalace_drawers`
- **SQLite knowledge graph**：保存带时间语义的结构化三元组事实

这套二分结构是仓库的核心设计：原文检索走语义向量库，显式事实关系走本地知识图谱。

## 主要数据流

### 1. 初始化与配置
- `mempalace/config.py` 的配置优先级是：环境变量 > `~/.mempalace/config.json` > 默认值。
- `mempalace/cli.py` 中的 `mempalace init <dir>` 会扫描项目文件中的实体、根据目录结构检测 rooms，并初始化用户级配置目录。
- 除非通过 `--palace` 或环境变量覆盖，否则默认 palace 路径在仓库外部的 `~/.mempalace/palace`。

### 2. 写入路径
有两条彼此独立、但最终都写入同一个 Chroma collection 的写入管线：

- **项目文件挖掘**：`mempalace/miner.py`
  - 遍历项目文件
  - 默认遵守 `.gitignore`
  - 强跳过生成物、缓存目录、依赖目录
  - 将可读文件切成带重叠的文本 drawers

- **对话挖掘**：`mempalace/convo_miner.py`
  - 通过 `mempalace/normalize.py` 统一多种导出格式
  - 主要按 exchange pair（`> user turn` + AI response）切块
  - 通过关键词或可选的通用提取逻辑为内容分配 room

关键架构点：这两条写入链路最终收敛到同一套 palace schema，因此上层搜索 / MCP 工具并不关心 drawer 来自源码、文档还是聊天记录。

### 3. 检索分层
检索能力按深度刻意拆成多层：

- `mempalace/searcher.py`：直接对 ChromaDB 做语义搜索，可按 wing / room 过滤
- `mempalace/layers.py`：构建 “wake-up” 分层上下文
  - **L0**：来自 `~/.mempalace/identity.txt` 的身份信息
  - **L1**：从 palace 中高优先级 drawers 生成的紧凑摘要
  - **L2**：按 wing / room 过滤的定向检索
  - **L3**：完整语义搜索

这是理解用户侧“记忆召回”的关键心智模型：始终加载轻量上下文，需要时再逐层深入。

### 4. MCP 服务层
`mempalace/mcp_server.py` 将 palace 暴露给外部 AI 工具。

从概念上看，它分成四类工具：
- **Palace 读写**：status、taxonomy、search、duplicate check、add/delete drawer
- **Knowledge graph**：add/query/invalidate/timeline/stats
- **Navigation graph**：跨 wing 遍历 rooms、查找 tunnels
- **Agent diary**：Agent 私有持久笔记

MCP server 不只是 search 的一层薄封装；它还会在 status 响应中嵌入仓库自己的 “Palace Protocol” 和 AAAK dialect 说明，让接入的 Agent 能通过服务端响应完成自举。

## 两种图结构，不要混淆
这个仓库里有两种“图”，用途不同：

- `mempalace/knowledge_graph.py`
  - SQLite 中的显式时间知识图谱
  - 适合表达“谁在什么时候做了什么 / 某个事实何时成立”这类结构化事实查询

- `mempalace/palace_graph.py`
  - 从 Chroma metadata 派生出的导航图
  - 节点是 rooms，边来自多个 wings 共享同名 room 时形成的 tunnels
  - 适合做跨项目 / 跨人物主题导航，而不是事实三元组查询

不要把两者视为同一种能力：前者是结构化事实源，后者是基于检索元数据推导出的导航层。

## AAAK 与压缩层
- `mempalace/dialect.py` 实现 AAAK 压缩方言。
- 当前文档明确把 AAAK 定义为 experimental 且 lossy。
- 默认存储仍然是 ChromaDB 中的原文文本；AAAK 是独立的压缩路径，用于上下文压缩、输出生成以及 `compress` 命令。

如果要修改检索或存储行为，要保留这个边界：文档里的 benchmark 主成绩是基于 raw 模式，而不是 AAAK 模式。

## 测试策略
测试体系的核心是“本地隔离存储”，而不是 mock 远程服务。

- `tests/conftest.py` 会在导入包模块之前，把 `HOME` / `USERPROFILE` 重写到临时目录。
- 这很重要，因为有些模块在 import 时就会初始化用户级存储，例如 MCP server 模块级的 knowledge graph 实例。
- 新测试通常应沿用这种模式：使用临时 Chroma collection 和临时 SQLite 数据库，而不是碰真实用户目录。

## 需要熟悉的 CLI 命令面
`mempalace/cli.py` 中主要的命令有：
- `init`
- `mine`（`projects` 或 `convos` 模式）
- `split`
- `search`
- `compress`
- `wake-up`
- `repair`
- `status`

其中 `split` 是处理拼接型 transcript 导出的预处理步骤；`repair` 用于在 palace 损坏时重建 Chroma collection。

## Hooks 与 Agent 工作流
`hooks/README.md` 记录了给 Claude Code / Codex 用的 shell hooks，用来在定期或上下文压缩前触发保存。这里最重要的设计点是：hook 脚本负责决定 **何时触发**，而 AI 负责决定 **保存什么内容进 MemPalace**。

## 修改代码时的定位方式
准备改动前，先判断你要动的是哪一层：

- CLI 参数与命令语义 → `mempalace/cli.py`
- 配置与默认路径 → `mempalace/config.py`
- 项目文件写入行为 → `mempalace/miner.py`
- 对话写入行为 → `mempalace/convo_miner.py`、`mempalace/normalize.py`
- 搜索行为 → `mempalace/searcher.py`、`mempalace/layers.py`
- MCP 工具协议 → `mempalace/mcp_server.py`
- 结构化事实处理 → `mempalace/knowledge_graph.py`
- 跨 wing 主题导航 → `mempalace/palace_graph.py`
