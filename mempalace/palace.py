"""
palace.py — Shared palace operations.

Consolidates ChromaDB access patterns used by both miners and the MCP server.
Provides process-level caching to avoid redundant client/model initialization.
"""

import os
import chromadb

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    "coverage",
    ".mempalace",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    ".ipynb_checkpoints",
    ".eggs",
    "htmlcov",
    "target",
}

# ---------------------------------------------------------------------------
# Process-level cache: keeps one PersistentClient and one embedding function
# per palace_path to avoid re-creating them on every call.
# ---------------------------------------------------------------------------
_client_cache: dict = {}       # palace_path -> chromadb.PersistentClient
_embedding_fn_cache = None     # shared embedding function (config-driven)
_embedding_fn_loaded = False   # distinguish None (default) from "not loaded"


def _get_client(palace_path: str):
    """Return a cached PersistentClient for *palace_path*."""
    if palace_path not in _client_cache:
        _client_cache[palace_path] = chromadb.PersistentClient(path=palace_path)
    return _client_cache[palace_path]


def _get_embedding_fn():
    """Return the configured embedding function (cached, lazy-loaded once)."""
    global _embedding_fn_cache, _embedding_fn_loaded
    if not _embedding_fn_loaded:
        from .config import MempalaceConfig
        from .embedding import get_embedding_function

        config = MempalaceConfig()
        _embedding_fn_cache = get_embedding_function(
            config.embedding_model, config.embedding_device, config.embedding_dtype
        )
        _embedding_fn_loaded = True
    return _embedding_fn_cache


def get_collection(palace_path: str, collection_name: str = "mempalace_drawers"):
    """Get or create the palace ChromaDB collection."""
    os.makedirs(palace_path, exist_ok=True)
    try:
        os.chmod(palace_path, 0o700)
    except (OSError, NotImplementedError):
        pass

    client = _get_client(palace_path)
    embedding_fn = _get_embedding_fn()

    kwargs = {"name": collection_name}
    if embedding_fn:
        kwargs["embedding_function"] = embedding_fn

    try:
        return client.get_collection(**kwargs)
    except Exception:
        if embedding_fn:
            return client.create_collection(collection_name, embedding_function=embedding_fn)
        else:
            return client.create_collection(collection_name)


def open_collection(palace_path: str, collection_name: str = "mempalace_drawers"):
    """Open an existing palace collection (read-only, no auto-create).

    Raises ValueError if the collection doesn't exist.
    """
    client = _get_client(palace_path)
    embedding_fn = _get_embedding_fn()

    kwargs = {"name": collection_name}
    if embedding_fn:
        kwargs["embedding_function"] = embedding_fn

    return client.get_collection(**kwargs)


def get_embedding_function_cached():
    """Public accessor for the cached embedding function.

    Used by callers that need to call ``encode_query_texts()``
    with the project-wide embedding function.
    """
    return _get_embedding_fn()


def file_already_mined(collection, source_file: str, check_mtime: bool = False) -> bool:
    """Check if a file has already been filed in the palace.

    When check_mtime=True (used by project miner), returns False if the file
    has been modified since it was last mined, so it gets re-mined.
    When check_mtime=False (used by convo miner), just checks existence.
    """
    try:
        results = collection.get(where={"source_file": source_file}, limit=1)
        if not results.get("ids"):
            return False
        if check_mtime:
            stored_meta = results.get("metadatas", [{}])[0]
            stored_mtime = stored_meta.get("source_mtime")
            if stored_mtime is None:
                return False
            current_mtime = os.path.getmtime(source_file)
            return float(stored_mtime) == current_mtime
        return True
    except Exception:
        return False
