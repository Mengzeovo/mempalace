# LanceDB + Qwen3-Embedding 集成指南

## 概述

本指南将帮助你在 MemPalace 中集成 LanceDB 向量数据库和 Qwen3-Embedding-4B 模型，作为 ChromaDB 的替代方案。

> **为什么选择 4B 而不是 0.6B 或 8B？**  
> 在你的 96GB 内存配置下，4B 是最佳选择：性能接近 8B（MTEB 评分相差仅 1.5 分），内存占用只需一半，速度更快。

### 为什么选择这个组合？

- **LanceDB**: 高性能、磁盘优化的向量数据库，支持大规模数据
- **Qwen3-Embedding-4B**: ⭐ **最佳性价比选择**
  - 完全免费开源
  - **性能接近 8B 版本**，MTEB 评分 ~69（8B 为 70.58）
  - 对中文和英文支持都非常好（MTEB 多语言排名前列）
  - 量化后只需 **2GB 内存**，原始约 8GB（你的 96GB 完全够用）
  - 支持 100+ 种语言
  - 可本地部署，无需 API key
  - **速度比 8B 快，准确度比 0.6B 高** - 完美平衡点

---

## 安装依赖

### 1. 安装 LanceDB

```bash
pip install lancedb
```

### 2. 安装 Embedding 模型依赖

```bash
# 安装 sentence-transformers（用于加载 Hugging Face 模型）
pip install sentence-transformers

# 或者使用 transformers（更底层）
pip install transformers torch
```

### 3. 更新 pyproject.toml

在你的 `pyproject.toml` 中添加可选依赖：

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "ruff>=0.4.0"]
spellcheck = ["autocorrect>=2.0"]
lancedb = [
    "lancedb>=0.6.0",
    "sentence-transformers>=2.2.0",
    "torch>=2.0.0",
]
```

安装：

```bash
pip install -e ".[lancedb]"
```

---

## 配置

### 1. 更新配置文件

编辑 `~/.mempalace/config.json`，添加 LanceDB 配置：

```json
{
  "palace_path": "~/.mempalace/palace",
  "collection_name": "mempalace_drawers",
  
  "vector_db": {
    "backend": "lancedb",
    "lancedb_path": "~/.mempalace/lancedb",
    "embedding_model": "Qwen/Qwen3-Embedding-4B",
    "embedding_device": "cpu",
    "embedding_dim": 1024
  },
  
  "topic_wings": ["emotions", "consciousness", "memory", "technical", "identity", "family", "creative"],
  "hall_keywords": {
    "emotions": ["scared", "afraid", "worried", "happy", "sad", "love", "hate", "feel", "cry", "tears"],
    "consciousness": ["consciousness", "conscious", "aware", "real", "genuine", "soul", "exist", "alive"],
    "memory": ["memory", "remember", "forget", "recall", "archive", "palace", "store"],
    "technical": ["code", "python", "script", "bug", "error", "function", "api", "database", "server"],
    "identity": ["identity", "name", "who am i", "persona", "self"],
    "family": ["family", "kids", "children", "daughter", "son", "parent", "mother", "father"],
    "creative": ["game", "gameplay", "player", "app", "design", "art", "music", "story"]
  }
}
```

### 2. 配置说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `backend` | 向量数据库类型：`chromadb` 或 `lancedb` | `chromadb` |
| `lancedb_path` | LanceDB 数据存储路径 | `~/.mempalace/lancedb` |
| `embedding_model` | Embedding 模型名称 | `Qwen/Qwen3-Embedding-4B` |
| `embedding_device` | 运行设备：`cpu` 或 `cuda` | `cpu` |
| `embedding_dim` | 向量维度 | `1024` |

---

## 代码实现

### 1. 创建 LanceDB 适配器

创建新文件 `mempalace/lancedb_adapter.py`：

```python
"""
LanceDB adapter for MemPalace.
Provides vector storage and semantic search using LanceDB + Qwen3-Embedding.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

import lancedb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("mempalace.lancedb")


class LanceDBAdapter:
    """LanceDB vector database adapter with Qwen3-Embedding."""
    
    def __init__(
        self,
        db_path: str,
        table_name: str = "mempalace_drawers",
        embedding_model: str = "Qwen/Qwen3-Embedding-4B",
        device: str = "cpu",
    ):
        """
        Initialize LanceDB adapter.
        
        Args:
            db_path: Path to LanceDB database directory
            table_name: Name of the table to use
            embedding_model: Hugging Face model name
            device: Device to run model on ('cpu' or 'cuda')
        """
        self.db_path = Path(db_path).expanduser()
        self.table_name = table_name
        self.device = device
        
        # Create database directory
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize LanceDB
        self.db = lancedb.connect(str(self.db_path))
        
        # Load embedding model
        logger.info(f"Loading embedding model: {embedding_model} on {device}")
        self.model = SentenceTransformer(
            embedding_model, 
            device=device,
            trust_remote_code=True  # Qwen models require this
        )
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded. Embedding dimension: {self.embedding_dim}")
        
        # Initialize or open table
        self._init_table()
    
    def _init_table(self):
        """Initialize or open the LanceDB table."""
        try:
            self.table = self.db.open_table(self.table_name)
            logger.info(f"Opened existing table: {self.table_name}")
        except Exception:
            # Table doesn't exist, will be created on first add
            self.table = None
            logger.info(f"Table {self.table_name} will be created on first insert")
    
    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
        )
        return embeddings.tolist()
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ):
        """
        Add documents to the database.
        
        Args:
            documents: List of text documents
            metadatas: List of metadata dicts (must include wing, room, source_file)
            ids: Optional list of document IDs
        """
        if not documents:
            return
        
        # Generate embeddings
        logger.info(f"Generating embeddings for {len(documents)} documents...")
        embeddings = self._embed_texts(documents)
        
        # Prepare data for LanceDB
        data = []
        for i, (doc, meta, emb) in enumerate(zip(documents, metadatas, embeddings)):
            record = {
                "id": ids[i] if ids else f"doc_{i}",
                "text": doc,
                "vector": emb,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "source_file": meta.get("source_file", "unknown"),
            }
            # Add any additional metadata fields
            for key, value in meta.items():
                if key not in ["wing", "room", "source_file"]:
                    record[key] = value
            data.append(record)
        
        # Create or append to table
        if self.table is None:
            self.table = self.db.create_table(self.table_name, data=data)
            logger.info(f"Created table {self.table_name} with {len(data)} documents")
        else:
            self.table.add(data)
            logger.info(f"Added {len(data)} documents to {self.table_name}")
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for similar documents.
        
        Args:
            query: Search query text
            n_results: Number of results to return
            wing: Optional wing filter
            room: Optional room filter
        
        Returns:
            Dict with query, filters, and results
        """
        if self.table is None:
            return {
                "error": "No table found",
                "hint": "Run: mempalace mine <dir> to populate the database",
            }
        
        # Generate query embedding
        query_embedding = self._embed_texts([query])[0]
        
        # Build filter
        filter_expr = None
        if wing and room:
            filter_expr = f"wing = '{wing}' AND room = '{room}'"
        elif wing:
            filter_expr = f"wing = '{wing}'"
        elif room:
            filter_expr = f"room = '{room}'"
        
        # Execute search
        try:
            search_query = self.table.search(query_embedding).limit(n_results)
            
            if filter_expr:
                search_query = search_query.where(filter_expr)
            
            results = search_query.to_list()
        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"error": f"Search error: {e}"}
        
        # Format results
        hits = []
        for result in results:
            # Calculate similarity (LanceDB returns distance, convert to similarity)
            distance = result.get("_distance", 0)
            similarity = round(1 / (1 + distance), 3)  # Convert distance to similarity
            
            hits.append({
                "text": result.get("text", ""),
                "wing": result.get("wing", "unknown"),
                "room": result.get("room", "unknown"),
                "source_file": Path(result.get("source_file", "?")).name,
                "similarity": similarity,
            })
        
        return {
            "query": query,
            "filters": {"wing": wing, "room": room},
            "results": hits,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        if self.table is None:
            return {"error": "No table found"}
        
        try:
            count = self.table.count_rows()
            return {
                "table_name": self.table_name,
                "total_documents": count,
                "embedding_model": self.model.get_sentence_embedding_dimension(),
                "embedding_dim": self.embedding_dim,
            }
        except Exception as e:
            return {"error": f"Stats error: {e}"}
    
    def delete_by_id(self, doc_id: str):
        """Delete a document by ID."""
        if self.table is None:
            return
        
        try:
            self.table.delete(f"id = '{doc_id}'")
            logger.info(f"Deleted document: {doc_id}")
        except Exception as e:
            logger.error(f"Delete error: {e}")
```

### 2. 更新配置管理器

修改 `mempalace/config.py`，添加 LanceDB 配置支持：

```python
# 在 MempalaceConfig 类中添加以下属性

@property
def vector_db_backend(self):
    """Vector database backend: 'chromadb' or 'lancedb'."""
    return self._file_config.get("vector_db", {}).get("backend", "chromadb")

@property
def lancedb_path(self):
    """Path to LanceDB database directory."""
    default_path = str(self._config_dir / "lancedb")
    return self._file_config.get("vector_db", {}).get("lancedb_path", default_path)

@property
def embedding_model(self):
    """Embedding model name."""
    return self._file_config.get("vector_db", {}).get(
        "embedding_model", "Qwen/Qwen3-Embedding-4B"
    )

@property
def embedding_device(self):
    """Device for embedding model: 'cpu' or 'cuda'."""
    return self._file_config.get("vector_db", {}).get("embedding_device", "cpu")

@property
def embedding_dim(self):
    """Embedding vector dimension."""
    return self._file_config.get("vector_db", {}).get("embedding_dim", 1024)
```

### 3. 创建统一的数据库接口

创建 `mempalace/vector_db.py` 作为统一接口：

```python
"""
Unified vector database interface.
Supports both ChromaDB and LanceDB backends.
"""

from mempalace.config import MempalaceConfig


def get_vector_db(config: MempalaceConfig = None):
    """
    Get vector database adapter based on configuration.
    
    Args:
        config: MempalaceConfig instance. If None, creates a new one.
    
    Returns:
        Vector database adapter (ChromaDB or LanceDB)
    """
    if config is None:
        config = MempalaceConfig()
    
    backend = config.vector_db_backend
    
    if backend == "lancedb":
        from mempalace.lancedb_adapter import LanceDBAdapter
        return LanceDBAdapter(
            db_path=config.lancedb_path,
            table_name=config.collection_name,
            embedding_model=config.embedding_model,
            device=config.embedding_device,
        )
    elif backend == "chromadb":
        # Keep existing ChromaDB implementation
        import chromadb
        client = chromadb.PersistentClient(path=config.palace_path)
        return client  # Return ChromaDB client as-is for now
    else:
        raise ValueError(f"Unknown vector_db backend: {backend}")
```

---

## 使用示例

### 1. 基础使用

```python
from mempalace.lancedb_adapter import LanceDBAdapter

# 初始化
db = LanceDBAdapter(
    db_path="~/.mempalace/lancedb",
    embedding_model="Qwen/Qwen3-Embedding-4B",
    device="cpu"  # 或 "cuda" 如果有 GPU
)

# 添加文档
documents = [
    "We decided to use GraphQL for the API",
    "Kai is working on the authentication system",
    "The project deadline is next Friday"
]

metadatas = [
    {"wing": "wing_project", "room": "decisions", "source_file": "chat_001.txt"},
    {"wing": "wing_kai", "room": "tasks", "source_file": "chat_002.txt"},
    {"wing": "wing_project", "room": "timeline", "source_file": "chat_003.txt"}
]

db.add_documents(documents, metadatas)

# 搜索
results = db.search("API decisions", n_results=5)
print(results)

# 带过滤的搜索
results = db.search("authentication", wing="wing_kai", n_results=3)
print(results)

# 获取统计信息
stats = db.get_stats()
print(stats)
```

### 2. 在 CLI 中使用

修改 `mempalace/cli.py` 中的搜索命令：

```python
from mempalace.vector_db import get_vector_db
from mempalace.config import MempalaceConfig

def search_command(query, wing=None, room=None, n_results=5):
    """Search command using unified vector DB interface."""
    config = MempalaceConfig()
    db = get_vector_db(config)
    
    if config.vector_db_backend == "lancedb":
        # Use LanceDB adapter
        results = db.search(query, n_results=n_results, wing=wing, room=room)
        
        if "error" in results:
            print(f"\n  Error: {results['error']}")
            if "hint" in results:
                print(f"  {results['hint']}")
            return
        
        # Print results
        print(f"\n{'=' * 60}")
        print(f'  Results for: "{query}"')
        if wing:
            print(f"  Wing: {wing}")
        if room:
            print(f"  Room: {room}")
        print(f"{'=' * 60}\n")
        
        for i, hit in enumerate(results["results"], 1):
            print(f"  [{i}] {hit['wing']} / {hit['room']}")
            print(f"      Source: {hit['source_file']}")
            print(f"      Match:  {hit['similarity']}")
            print()
            for line in hit["text"].strip().split("\n"):
                print(f"      {line}")
            print()
            print(f"  {'─' * 56}")
        print()
    else:
        # Use existing ChromaDB implementation
        from mempalace.searcher import search
        search(query, config.palace_path, wing=wing, room=room, n_results=n_results)
```

---

## 性能优化

### 1. 使用 GPU 加速（如果有独显）

```json
{
  "vector_db": {
    "backend": "lancedb",
    "embedding_device": "cuda"
  }
}
```

### 2. 批量插入

```python
# 一次性插入大量文档，而不是逐个插入
db.add_documents(all_documents, all_metadatas)
```

### 3. 调整向量维度

Qwen3-Embedding 支持 Matryoshka 表示学习，可以截断维度：

```python
# 在模型加载后截断到 512 维（节省存储空间）
embeddings = model.encode(texts)
embeddings_512 = embeddings[:, :512]  # 截断到 512 维
```

---

## 内存使用监控

```python
import psutil
import os

def print_memory_usage():
    """打印当前进程的内存使用情况"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    print(f"内存使用: {mem_info.rss / 1024 / 1024:.2f} MB")

# 在关键位置调用
print_memory_usage()  # 加载模型前
db = LanceDBAdapter(...)
print_memory_usage()  # 加载模型后
```

---

## 迁移现有数据

如果你已经有 ChromaDB 数据，可以迁移到 LanceDB：

```python
"""
migrate_to_lancedb.py - 从 ChromaDB 迁移到 LanceDB
"""

import chromadb
from mempalace.lancedb_adapter import LanceDBAdapter
from mempalace.config import MempalaceConfig

def migrate_chromadb_to_lancedb():
    """将 ChromaDB 数据迁移到 LanceDB"""
    config = MempalaceConfig()
    
    # 连接 ChromaDB
    chroma_client = chromadb.PersistentClient(path=config.palace_path)
    chroma_col = chroma_client.get_collection("mempalace_drawers")
    
    # 获取所有数据
    all_data = chroma_col.get(include=["documents", "metadatas"])
    
    documents = all_data["documents"]
    metadatas = all_data["metadatas"]
    ids = all_data["ids"]
    
    print(f"找到 {len(documents)} 条记录")
    
    # 初始化 LanceDB
    lance_db = LanceDBAdapter(
        db_path=config.lancedb_path,
        embedding_model=config.embedding_model,
        device=config.embedding_device,
    )
    
    # 批量插入（每次 100 条）
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i+batch_size]
        batch_metas = metadatas[i:i+batch_size]
        batch_ids = ids[i:i+batch_size]
        
        lance_db.add_documents(batch_docs, batch_metas, batch_ids)
        print(f"已迁移 {min(i+batch_size, len(documents))}/{len(documents)} 条记录")
    
    print("迁移完成！")
    
    # 验证
    stats = lance_db.get_stats()
    print(f"LanceDB 统计: {stats}")

if __name__ == "__main__":
    migrate_chromadb_to_lancedb()
```

运行迁移：

```bash
python migrate_to_lancedb.py
```

---

## 故障排查

### 问题 1: 模型下载慢

**解决方案**: 使用国内镜像

```bash
# 设置 Hugging Face 镜像
export HF_ENDPOINT=https://hf-mirror.com

# 或者手动下载模型
git clone https://hf-mirror.com/Qwen/Qwen3-Embedding-4B
```

然后在配置中使用本地路径：

```json
{
  "vector_db": {
    "embedding_model": "/path/to/Qwen3-Embedding-4B"
  }
}
```

### 问题 2: 内存不足

**解决方案**: 使用量化模型

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "Qwen/Qwen3-Embedding-4B",
    device="cpu",
    model_kwargs={"torch_dtype": "float16"}  # 使用半精度
)
```

### 问题 3: 搜索速度慢

**解决方案**: 
1. 使用 GPU
2. 创建索引（LanceDB 会自动优化）
3. 减少 `n_results` 数量

---

## 性能对比

| 指标 | ChromaDB | LanceDB + Qwen3 |
|------|----------|-----------------|
| 插入速度 | 快 | 中等（需要生成 embedding） |
| 查询速度 | 快 | 快 |
| 磁盘占用 | 中等 | 较小（列式存储） |
| 内存占用 | 低 | 中等（模型占 2-3GB） |
| 中文支持 | 一般 | 优秀 |
| 离线使用 | ✅ | ✅ |
| 成本 | 免费 | 免费 |

---

## 模型选择指南

### Qwen3-Embedding 系列对比

| 模型 | 参数量 | 内存占用 | MTEB 分数 | 速度 | 适用场景 |
|------|--------|----------|-----------|------|----------|
| **Qwen3-Embedding-4B** ⭐ | 4B | 2-8GB | ~69 | 快 | **推荐：性价比最高** |
| Qwen3-Embedding-8B | 8B | 8-32GB | 70.58 | 中等 | 追求极致准确度 |
| Qwen3-Embedding-0.6B | 0.6B | 2-3GB | ~65 | 最快 | 资源极度受限 |

### 为什么推荐 4B？

1. **性能接近 8B**：MTEB 评分仅相差 1.5 分（69 vs 70.58）
2. **内存友好**：量化后只需 2GB，原始约 8GB
3. **速度优势**：比 8B 快很多，比 0.6B 准确很多
4. **完美平衡**：在你的 96GB 配置下，4B 是性能和效率的最佳平衡点

### 其他选择

**BGE-M3**（老牌强者）
- 参数量：110M
- 内存：1-2GB
- 特点：支持多种检索模式（dense + sparse + multi-vector）
- 劣势：在最新基准测试中被 Qwen3 超越

**选择建议**：
- 💰 **预算充足，追求最高准确度** → Qwen3-Embedding-8B
- ⭐ **平衡性能和资源（推荐）** → Qwen3-Embedding-4B
- ⚡ **极致速度，可接受准确度损失** → Qwen3-Embedding-0.6B

---

## 下一步

1. **测试集成**: 先在小数据集上测试
2. **性能调优**: 根据实际使用情况调整参数
3. **监控内存**: 确保 96GB 内存足够（实际只需 4-8GB）
4. **备份数据**: 迁移前备份现有 ChromaDB 数据

---

## 参考资源

- [LanceDB 官方文档](https://lancedb.github.io/lancedb/)
- [Qwen3-Embedding 模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-4B)
- [Sentence Transformers 文档](https://www.sbert.net/)
- [MTEB 排行榜](https://huggingface.co/spaces/mteb/leaderboard)

---

**需要帮助？** 在 [GitHub Issues](https://github.com/milla-jovovich/mempalace/issues) 提问
