import os
import tempfile
import shutil
from mempalace.convo_miner import mine_convos
from mempalace.palace import open_collection


def test_convo_mining():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "chat.txt"), "w") as f:
        f.write(
            "> What is memory?\nMemory is persistence.\n\n> Why does it matter?\nIt enables continuity.\n\n> How do we build it?\nWith structured storage.\n"
        )

    palace_path = os.path.join(tmpdir, "palace")
    mine_convos(tmpdir, palace_path, wing="test_convos")

    # Use palace.open_collection so the same embedding function (_FakeEmbedding
    # injected by conftest) is used for both write and query — avoids dimension
    # mismatch when ChromaDB's default ONNX embedding is not available.
    col = open_collection(palace_path)
    assert col.count() >= 2

    # Verify search works
    results = col.query(query_texts=["memory persistence"], n_results=1)
    assert len(results["documents"][0]) > 0

    shutil.rmtree(tmpdir, ignore_errors=True)
