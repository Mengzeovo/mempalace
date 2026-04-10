# MemPalace 中文 Embedding 支持指南

## 快速开始

### 1. 安装中文 embedding 依赖

```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装中文支持
pip install sentence-transformers
```

### 2. 配置中文 embedding 模型

编辑或创建 `~/.mempalace/config.json`：

```json
{
  "palace_path": "~/.mempalace/palace",
  "collection_name": "mempalace_drawers",
  "embedding_model": "BAAI/bge-m3"
}
```

### 3. 重新索引（重要！）

**注意：更换 embedding 模型后，必须删除旧数据并重新索引**

```powershell
# 备份旧数据（可选）
Move-Item ~\.mempalace\palace ~\.mempalace\palace.backup

# 重新索引
mempalace mine .
```

### 4. 重启 MCP 服务器

```powershell
pm2 restart mempalace-mcp
```

## 推荐的 Embedding 模型

| 模型 | 大小 | 优势 | 适用场景 |
|------|------|------|---------|
| **BAAI/bge-m3** ⭐ | 560MB | 中英文都好，支持100+语言 | **推荐：通用场景** |
| BAAI/bge-small-zh-v1.5 | 102MB | 小巧快速 | 资源受限 |
| Qwen/Qwen3-Embedding-4B | 8GB | 最佳质量 | 追求极致准确度 |
| default | 90MB | ChromaDB 默认 | 仅英文 |

## 配置示例

### 通用场景（推荐）

```json
{
  "embedding_model": "BAAI/bge-m3"
}
```

### 小内存场景

```json
{
  "embedding_model": "BAAI/bge-small-zh-v1.5"
}
```

### 追求最佳质量

```json
{
  "embedding_model": "Qwen/Qwen3-Embedding-4B"
}
```

### 仅英文（默认）

```json
{
  "embedding_model": "default"
}
```

或者不配置 `embedding_model` 字段。

## 完整配置示例

参考 `config-chinese-example.json`：

```json
{
  "palace_path": "~/.mempalace/palace",
  "collection_name": "mempalace_drawers",
  "embedding_model": "BAAI/bge-m3",
  
  "topic_wings": [
    "情感", "意识", "记忆", "技术", "身份", "家庭", "创意"
  ],
  
  "hall_keywords": {
    "技术": [
      "代码", "脚本", "错误", "函数", "数据库",
      "code", "python", "script", "bug", "error"
    ]
  }
}
```

## 测试中文搜索

```powershell
# 索引中文内容
mempalace mine .

# 测试中文搜索
mempalace search "如何实现 MCP 服务器"
mempalace search "中文支持"
mempalace search "embedding 模型"
```

## 常见问题

### Q: 更换模型后搜索结果不对？

A: 必须删除旧的 palace 数据并重新索引：

```powershell
Remove-Item -Recurse -Force ~\.mempalace\palace
mempalace mine .
```

### Q: 模型下载慢？

A: 使用国内镜像：

```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
mempalace mine .
```

### Q: 内存不足？

A: 使用更小的模型：

```json
{
  "embedding_model": "BAAI/bge-small-zh-v1.5"
}
```

### Q: 想用回默认模型？

A: 设置为 "default" 或删除配置：

```json
{
  "embedding_model": "default"
}
```

然后重新索引。

## 性能对比

| 模型 | 中文支持 | 英文支持 | 内存占用 | 速度 |
|------|---------|---------|---------|------|
| BAAI/bge-m3 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ~1GB | 快 |
| bge-small-zh-v1.5 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ~300MB | 很快 |
| Qwen3-Embedding-4B | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ~8GB | 中等 |
| default (all-MiniLM) | ⭐ | ⭐⭐⭐⭐⭐ | ~100MB | 很快 |

## 注意事项

1. **更换模型必须重新索引** - embedding 向量不兼容
2. **首次使用会下载模型** - 需要网络连接
3. **模型存储在 ~/.cache/huggingface** - 可以手动清理
4. **中英文混合内容推荐 bge-m3** - 平衡性能和质量

## 验证配置

```powershell
# 查看当前配置
cat ~\.mempalace\config.json

# 测试搜索
mempalace search "测试中文"
mempalace search "test english"
```

## 参考资源

- [BGE-M3 模型](https://huggingface.co/BAAI/bge-m3)
- [Qwen3-Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-4B)
- [Sentence Transformers 文档](https://www.sbert.net/)
