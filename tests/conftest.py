"""
conftest.py — Shared fixtures for MemPalace tests.

Provides isolated palace and knowledge graph instances so tests never
touch the user's real data or leak temp files on failure.

HOME is redirected to a temp directory at module load time — before any
mempalace imports — so that module-level initialisations (e.g.
``_kg = KnowledgeGraph()`` in mcp_server) write to a throwaway location
instead of the real user profile.
"""

import os
import shutil
import tempfile
from unittest.mock import patch

# ── Isolate HOME before any mempalace imports ──────────────────────────
_original_env = {}
_session_tmp = tempfile.mkdtemp(prefix="mempalace_session_")

# Preserve HuggingFace / sentence-transformers cache dirs so that
# already-downloaded models (e.g. Qwen3-Embedding-4B) are still found
# even after HOME is redirected.  Tests that call mine() are expected to
# mock the embedding function anyway (see _mock_embedding_fn below).
for _var in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH"):
    _original_env[_var] = os.environ.get(_var)

_real_home = _original_env.get("USERPROFILE") or _original_env.get("HOME") or ""
for _cache_var in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "SENTENCE_TRANSFORMERS_HOME"):
    if not os.environ.get(_cache_var):
        _default = os.path.join(_real_home, ".cache", "huggingface")
        os.environ[_cache_var] = _default

os.environ["HOME"] = _session_tmp
os.environ["USERPROFILE"] = _session_tmp
os.environ["HOMEDRIVE"] = os.path.splitdrive(_session_tmp)[0] or "C:"
os.environ["HOMEPATH"] = os.path.splitdrive(_session_tmp)[1] or _session_tmp

# Now it is safe to import mempalace modules that trigger initialisation.
import pytest  # noqa: E402

from mempalace.config import MempalaceConfig  # noqa: E402
from mempalace.knowledge_graph import KnowledgeGraph  # noqa: E402
from mempalace.palace import get_collection  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_embedding_fn():
    """Stub out embedding loading for all tests.

    We must patch both paths:
    1) ``palace._get_embedding_fn`` (used by miner/searcher/palace helpers)
    2) ``embedding.get_embedding_function`` (used directly by mcp_server)

    This guarantees tests never load Qwen3-Embedding-4B and never trigger
    ChromaDB's fallback ONNX download.
    """
    import mempalace.embedding as _embedding
    import mempalace.palace as _palace
    import chromadb.utils.embedding_functions as _chroma_efs
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

    class _FakeEmbedding(EmbeddingFunction):
        """Fast deterministic embedding for tests.

        Produces normalized bag-of-words hash vectors so semantic tests keep
        meaningful ordering (unlike all-zero vectors), while never loading any
        external model.
        """

        _dims = 128

        def __call__(self, input: Documents) -> Embeddings:
            import hashlib
            import math
            import re

            vectors = []
            for text in input:
                vec = [0.0] * self._dims
                tokens = re.findall(r"\w+", (text or "").lower())
                if not tokens:
                    vectors.append(vec)
                    continue

                for tok in tokens:
                    h = hashlib.md5(tok.encode("utf-8")).digest()
                    idx = int.from_bytes(h[:2], "big") % self._dims
                    sign = 1.0 if (h[2] % 2 == 0) else -1.0
                    vec[idx] += sign

                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]
                vectors.append(vec)

            return vectors

    _fake = _FakeEmbedding()

    _palace._embedding_fn_cache = None
    _palace._embedding_fn_loaded = False

    with (
        patch.object(_palace, "_get_embedding_fn", new=lambda: _fake),
        patch.object(_embedding, "get_embedding_function", new=lambda *args, **kwargs: _fake),
        patch.object(_chroma_efs, "DefaultEmbeddingFunction", new=lambda *args, **kwargs: _fake),
    ):
        yield

    _palace._embedding_fn_cache = None
    _palace._embedding_fn_loaded = False
    _palace._client_cache.clear()


@pytest.fixture(autouse=True)
def _reset_mcp_cache():
    """Reset the MCP server's cached ChromaDB client/collection between tests."""

    def _clear_cache():
        try:
            from mempalace import mcp_server

            mcp_server._client_cache = None
            mcp_server._collection_cache = None
        except (ImportError, AttributeError):
            pass

    _clear_cache()
    yield
    _clear_cache()


@pytest.fixture(scope="session", autouse=True)
def _isolate_home():
    """Ensure HOME points to a temp dir for the entire test session.

    The env vars were already set at module level (above) so that
    module-level initialisations are captured.  This fixture simply
    restores the originals on teardown and cleans up the temp dir.
    """
    yield
    for var, orig in _original_env.items():
        if orig is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = orig
    shutil.rmtree(_session_tmp, ignore_errors=True)


@pytest.fixture
def tmp_dir():
    """Create and auto-cleanup a temporary directory."""
    d = tempfile.mkdtemp(prefix="mempalace_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def palace_path(tmp_dir):
    """Path to an empty palace directory inside tmp_dir."""
    p = os.path.join(tmp_dir, "palace")
    os.makedirs(p)
    return p


@pytest.fixture
def config(tmp_dir, palace_path):
    """A MempalaceConfig pointing at the temp palace."""
    cfg_dir = os.path.join(tmp_dir, "config")
    os.makedirs(cfg_dir)
    import json

    with open(os.path.join(cfg_dir, "config.json"), "w") as f:
        json.dump({"palace_path": palace_path}, f)
    return MempalaceConfig(config_dir=cfg_dir)


@pytest.fixture
def collection(palace_path):
    """A ChromaDB collection pre-seeded in the temp palace."""
    col = get_collection(palace_path)
    yield col
    del col


@pytest.fixture
def seeded_collection(collection):
    """Collection with a handful of representative drawers."""
    collection.add(
        ids=[
            "drawer_proj_backend_aaa",
            "drawer_proj_backend_bbb",
            "drawer_proj_frontend_ccc",
            "drawer_notes_planning_ddd",
        ],
        documents=[
            "The authentication module uses JWT tokens for session management. "
            "Tokens expire after 24 hours. Refresh tokens are stored in HttpOnly cookies.",
            "Database migrations are handled by Alembic. We use PostgreSQL 15 "
            "with connection pooling via pgbouncer.",
            "The React frontend uses TanStack Query for server state management. "
            "All API calls go through a centralized fetch wrapper.",
            "Sprint planning: migrate auth to passkeys by Q3. "
            "Evaluate ChromaDB alternatives for vector search.",
        ],
        metadatas=[
            {
                "wing": "project",
                "room": "backend",
                "source_file": "auth.py",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-01T00:00:00",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "db.py",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-02T00:00:00",
            },
            {
                "wing": "project",
                "room": "frontend",
                "source_file": "App.tsx",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-03T00:00:00",
            },
            {
                "wing": "notes",
                "room": "planning",
                "source_file": "sprint.md",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-04T00:00:00",
            },
        ],
    )
    return collection


@pytest.fixture
def kg(tmp_dir):
    """An isolated KnowledgeGraph using a temp SQLite file."""
    db_path = os.path.join(tmp_dir, "test_kg.sqlite3")
    return KnowledgeGraph(db_path=db_path)


@pytest.fixture
def seeded_kg(kg):
    """KnowledgeGraph pre-loaded with sample triples."""
    kg.add_entity("Alice", entity_type="person")
    kg.add_entity("Max", entity_type="person")
    kg.add_entity("swimming", entity_type="activity")
    kg.add_entity("chess", entity_type="activity")

    kg.add_triple("Alice", "parent_of", "Max", valid_from="2015-04-01")
    kg.add_triple("Max", "does", "swimming", valid_from="2025-01-01")
    kg.add_triple("Max", "does", "chess", valid_from="2024-06-01")
    kg.add_triple("Alice", "works_at", "Acme Corp", valid_from="2020-01-01", valid_to="2024-12-31")
    kg.add_triple("Alice", "works_at", "NewCo", valid_from="2025-01-01")

    return kg
