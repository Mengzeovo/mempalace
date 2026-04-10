"""
Embedding function utilities for MemPalace.
Provides Chinese-friendly embedding models.
"""

import logging
from typing import Optional

logger = logging.getLogger("mempalace.embedding")


def get_embedding_function(model_name: Optional[str] = None):
    """
    Get ChromaDB embedding function with Chinese support.
    
    Args:
        model_name: Model name. If None, uses default (BAAI/bge-m3).
                   Supported models:
                   - "BAAI/bge-m3" (recommended, 560M, good Chinese+English)
                   - "BAAI/bge-small-zh-v1.5" (small, 102M, Chinese-focused)
                   - "Qwen/Qwen3-Embedding-4B" (best, 4B, requires more memory)
                   - "default" (ChromaDB default, English-only)
    
    Returns:
        ChromaDB embedding function
    """
    from chromadb.utils import embedding_functions
    
    if model_name is None or model_name == "default":
        # Use ChromaDB default (all-MiniLM-L6-v2)
        logger.info("Using ChromaDB default embedding (English-only)")
        return None  # ChromaDB will use default
    
    try:
        logger.info(f"Loading embedding model: {model_name}")
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
        logger.info(f"Embedding model loaded: {model_name}")
        return ef
    except Exception as e:
        logger.warning(f"Failed to load {model_name}: {e}")
        logger.warning("Falling back to ChromaDB default embedding")
        return None


# Recommended models for different use cases
RECOMMENDED_MODELS = {
    "chinese": "BAAI/bge-m3",  # Best for Chinese+English
    "multilingual": "BAAI/bge-m3",  # Same, supports 100+ languages
    "small": "BAAI/bge-small-zh-v1.5",  # Smaller, faster, Chinese-focused
    "best": "Qwen/Qwen3-Embedding-4B",  # Best quality, needs more memory
    "default": None,  # ChromaDB default (English-only)
}
