import json
import tempfile
import unittest
from pathlib import Path

from kanban.config import load_config, validate_devlog_root, write_config
from kanban import store


class ConfigTests(unittest.TestCase):
    def test_config_round_trip_preserves_board_name_and_devlog_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            expected = {
                "board_name": "My Work Board",
                "devlog_root": "/tmp/my-devlog",
                "port": 9876,
            }

            write_config(expected, config_path)

            self.assertEqual(load_config(config_path), expected)

    def test_devlog_validation_requires_readable_root_catalog_and_scans_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "devlog"
            (root / "projects" / "sample" / "notes").mkdir(parents=True)
            (root / "AGENTS.md").write_text("Devlog instructions", encoding="utf-8")
            (root / "index.md").write_text("# Projects", encoding="utf-8")
            (root / "projects" / "sample" / "notes" / "one.md").write_text("Readable note", encoding="utf-8")

            self.assertEqual(validate_devlog_root(root), 1)

    def test_devlog_validation_rejects_skill_repository_without_data_root_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "projects").mkdir()

            with self.assertRaises(ValueError):
                validate_devlog_root(root)

    def test_new_board_starts_with_generic_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_db_path = store.DB_PATH
            store.DB_PATH = Path(temp_dir) / "kanban.db"
            try:
                connection = store.connect()
                self.assertEqual(
                    [column["name"] for column in store.board(connection)],
                    ["Backlog", "In Progress", "Done"],
                )
                connection.close()
            finally:
                store.DB_PATH = old_db_path


if __name__ == "__main__":
    unittest.main()
