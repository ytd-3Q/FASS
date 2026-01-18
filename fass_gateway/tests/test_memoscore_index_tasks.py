from __future__ import annotations

import sqlite3
import tempfile
import unittest


class TestMemoscoreIndexTasks(unittest.TestCase):
    def test_index_tasks_flow(self) -> None:
        import memoscore

        with tempfile.TemporaryDirectory() as td:
            core = memoscore.MemosCore(td, 4, 10_000)
            core.upsert_documents(
                "shared",
                [
                    {"path": "u://1", "content": "hello world", "embedding": [0.1, 0.2, 0.3, 0.4]},
                    {"path": "u://2", "content": "hello fass", "embedding": [0.2, 0.1, 0.0, 0.4]},
                ],
            )
            db = sqlite3.connect(f"{td}/memoscore.sqlite")
            c1 = db.execute("SELECT count(*) FROM index_tasks WHERE status!='done'").fetchone()[0]
            self.assertGreaterEqual(int(c1), 1)
            db.close()

            changed = int(core.sync_index_tasks(200))
            self.assertGreaterEqual(changed, 1)

            out = core.search(collection="shared", query_text="hello", query_vec=None, top_k=5)
            self.assertTrue(len(out) >= 1)


if __name__ == "__main__":
    unittest.main()
