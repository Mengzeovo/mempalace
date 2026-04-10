"""
Embedding function utilities for MemPalace.

Supports multilingual models including large decoder-only models
like Qwen3-Embedding-4B via sentence-transformers.
"""

import logging
from typing import Optional

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

logger = logging.getLogger("mempalace.embedding")

# Models that benefit from query instruction prefix.
# Maps model name prefix to the instruction string.
_QUERY_INSTRUCTION_MODELS = {
    "Qwen/Qwen3-Embedding": (
        "Instruct: Given a web search query, retrieve relevant passages "
        "that answer the query\nQuery:"
    ),
    "BAAI/bge-m3": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-small-zh": "为这个句子生成表示以用于检索相关文章：",
}

# Models known to need large-model kwargs (device_map, dtype, etc.)
_LARGE_MODELS = {"Qwen/Qwen3-Embedding-4B"}


class SentenceTransformerEmbedding(EmbeddingFunction[Documents]):
    """ChromaDB-compatible embedding function backed by sentence-transformers.

    Advantages over ChromaDB's built-in SentenceTransformerEmbeddingFunction:
    - Supports torch_dtype (fp16/bf16) to cut memory for large models
    - Supports device selection (cpu/cuda/auto)
    - Supports query instruction prefix for models that need it
    """

    def __init__(
        self,
        model_name: str,
        device: Optional[str] = None,
        dtype: Optional[str] = None,
    ):
        self._model_name = model_name
        self._device = device
        self._dtype = dtype
        self._model = None
        self._query_instruction: Optional[str] = None

        # Determine query instruction for this model
        for prefix, instruction in _QUERY_INSTRUCTION_MODELS.items():
            if model_name.startswith(prefix):
                self._query_instruction = instruction
                break

    def _load_model(self):
        """Lazy-load the model on first use."""
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        model_kwargs = {}
        if self._model_name in _LARGE_MODELS:
            model_kwargs["device_map"] = self._device or "auto"
            if self._dtype:
                import torch
                dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16}
                if self._dtype in dtype_map:
                    model_kwargs["torch_dtype"] = dtype_map[self._dtype]
            else:
                # Default large models to bfloat16
                import torch
                model_kwargs["torch_dtype"] = torch.bfloat16

        device = None if model_kwargs.get("device_map") else self._device

        logger.info("Loading embedding model: %s (device=%s, dtype=%s)",
                     self._model_name, self._device, self._dtype)

        self._model = SentenceTransformer(
            self._model_name,
            device=device,
            model_kwargs=model_kwargs,
            tokenizer_kwargs={"padding_side": "left"} if self._model_name in _LARGE_MODELS else {},
        )
        logger.info("Embedding model loaded: %s", self._model_name)

    def __call__(self, input: Documents) -> Embeddings:
        """Encode documents (storage path — no query instruction)."""
        self._load_model()
        embeddings = self._model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()

    def encode_queries(self, queries: Documents) -> Embeddings:
        """Encode queries with instruction prefix if the model supports it."""
        self._load_model()
        if self._query_instruction and hasattr(self._model, "encode"):
            # Try prompt_name first (sentence-transformers >= 2.7 with model config)
            try:
                embeddings = self._model.encode(
                    queries, prompt_name="query", normalize_embeddings=True
                )
                return embeddings.tolist()
            except Exception:
                pass
            # Fallback: manually prepend instruction
            prefixed = [self._query_instruction + q for q in queries]
            embeddings = self._model.encode(prefixed, normalize_embeddings=True)
            return embeddings.tolist()

        embeddings = self._model.encode(queries, normalize_embeddings=True)
        return embeddings.tolist()


def get_embedding_function(
    model_name: Optional[str] = None,
    device: Optional[str] = None,
    dtype: Optional[str] = None,
) -> Optional[EmbeddingFunction]:
    """
    Get ChromaDB-compatible embedding function.

    Args:
        model_name: Model name or "default" for ChromaDB built-in.
        device: Device for inference — "cpu", "cuda", "auto", or None.
        dtype: Data type — "float16", "bfloat16", or None (model default).

    Returns:
        EmbeddingFunction instance, or None for ChromaDB default.
    """
    if model_name is None or model_name == "default":
        logger.info("Using ChromaDB default embedding (English-only)")
        return None

    # Verify sentence-transformers is available before creating the function
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; falling back to ChromaDB default. "
            "Install with: pip install sentence-transformers"
        )
        return None

    try:
        return SentenceTransformerEmbedding(
            model_name=model_name,
            device=device,
            dtype=dtype,
        )
    except Exception as e:
        logger.warning("Failed to create embedding function for %s: %s", model_name, e)
        logger.warning("Falling back to ChromaDB default embedding")
        return None


# Recommended models for different use cases
RECOMMENDED_MODELS = {
    "chinese": "BAAI/bge-m3",
    "multilingual": "BAAI/bge-m3",
    "small": "BAAI/bge-small-zh-v1.5",
    "best": "Qwen/Qwen3-Embedding-4B",
    "default": None,
}
