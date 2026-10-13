import tempfile
import unittest
from pathlib import Path
import sqlite3
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from kanban import store
from kanban import server


class DevlogNoteDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.devlog_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_note(self, relative_path, content):
        path = self.devlog_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_finds_all_notes_in_nested_project_subfolders_by_exact_jira_key(self):
        expected_paths = (
            "projects/vend/notes/investigation.md",
            "projects/vend/bugs/nested/follow-up.md",
        )
        self.write_note(
            expected_paths[0],
            '---\ntitle: "Example investigation report"\n---\nDEMO-123 findings',
        )
        self.write_note(expected_paths[1], "Related to DEMO-123.")
        self.write_note("projects/vend/notes/other.md", "DEMO-1230 is a different ticket.")
        self.write_note("projects/vend/index.md", "DEMO-123 project summary")
        self.write_note("projects/vend/log.md", "DEMO-123 session log")
        self.write_note("projects/other/notes/unrelated.md", "DEMO-124 only")

        notes = store.find_devlog_notes("DEMO-123: Example invoice", self.devlog_root)

        notes_by_path = {note["path"]: note for note in notes}
        self.assertEqual(set(notes_by_path), set(expected_paths))
        self.assertEqual(notes_by_path[expected_paths[0]]["title"], "Example investigation report")
        self.assertEqual(notes_by_path[expected_paths[1]]["title"], "follow up")
        self.assertEqual(notes_by_path[expected_paths[0]]["jira_keys"], ["DEMO-123"])

    def test_deduplicates_same_note_matched_by_multiple_ticket_keys_in_title(self):
        self.write_note(
            "projects/vend/notes/shared-report.md",
            "DEMO-123 is the parent ticket and DEMO-124 is its backend task.",
        )

        notes = store.find_devlog_notes("DEMO-123 / DEMO-124: Example", self.devlog_root)

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["path"], "projects/vend/notes/shared-report.md")

    def test_extracts_keys_only_from_card_title(self):
        self.write_note("projects/vend/notes/child-ticket.md", "DEMO-124 backend details")
        self.write_note("projects/vend/notes/body-ticket.md", "DEMO-123 body details")

        notes = store.find_devlog_notes("Unkeyed title", self.devlog_root)

        self.assertEqual(notes, [])

    def test_returns_empty_for_missing_devlog_root_or_ticket_key(self):
        missing_root = self.devlog_root / "missing"

        self.assertEqual(store.find_devlog_notes("DEMO-123 task", missing_root), [])
        self.assertEqual(store.find_devlog_notes("No Jira key", self.devlog_root), [])

    def test_reads_current_note_content_and_rejects_paths_outside_project_subfolders(self):
        note_path = "vend/notes/current.md"
        self.write_note("projects/vend/notes/current.md", "# First version")
        self.write_note("projects/secrets.md", "not a project note")

        note = store.read_devlog_note(note_path, self.devlog_root)
        self.assertEqual(note["content"], "# First version")
        self.assertEqual(note["title"], "current")

        self.write_note("projects/vend/notes/current.md", "# Updated version")
        self.assertEqual(store.read_devlog_note(note_path, self.devlog_root)["content"], "# Updated version")
        self.assertIsNone(store.read_devlog_note("vend/../secrets.md", self.devlog_root))
        self.assertIsNone(store.read_devlog_note("../../AGENTS.md", self.devlog_root))
        self.assertIsNone(store.read_devlog_note("vend/index.md", self.devlog_root))
        self.assertIsNone(store.read_devlog_note("vend/missing.md", self.devlog_root))

    def test_existing_cards_migrate_and_generated_note_field_syncs_without_editing_card(self):
        old_db = self.devlog_root / "old.db"
        connection = sqlite3.connect(old_db)
        connection.executescript("""
            CREATE TABLE columns(id INTEGER PRIMARY KEY, name TEXT, position REAL, collapsed INTEGER DEFAULT 0);
            CREATE TABLE cards(id INTEGER PRIMARY KEY, column_id INTEGER, position REAL, marker TEXT DEFAULT '',
                title TEXT, content TEXT DEFAULT '', tags TEXT DEFAULT '[]', done INTEGER DEFAULT 0,
                done_date TEXT DEFAULT '', created_at TEXT, updated_at TEXT);
            CREATE TABLE card_events(id INTEGER PRIMARY KEY, card_id INTEGER, at TEXT, type TEXT,
                from_col TEXT, to_col TEXT, detail TEXT DEFAULT '');
            INSERT INTO columns(id, name, position) VALUES(1, 'Ongoing', 1);
            INSERT INTO cards(id, column_id, position, title, content, created_at, updated_at)
                VALUES(42, 1, 1, 'DEMO-123 / DEMO-124: Example invoice', 'Existing description', 'created', 'updated');
        """)
        connection.commit()
        connection.close()

        original_db_path = store.DB_PATH
        original_devlog_root = store.DEVLOG_ROOT
        store.DB_PATH = old_db
        store.DEVLOG_ROOT = self.devlog_root
        try:
            db = store.connect()
            self.write_note("projects/vend/notes/report.md", "---\ntitle: \"Investigation\"\n---\nDEMO-123 and DEMO-124")
            cards = store.board(db)[0]["cards"]
            self.assertEqual(len(cards[0]["devlog_notes"]), 1)
            self.assertEqual(cards[0]["devlog_notes"][0]["title"], "Investigation")
            self.assertEqual(cards[0]["content"], "Existing description")
            self.assertEqual(cards[0]["updated_at"], "updated")

            self.write_note("projects/vend/notes/report.md", "---\ntitle: \"Updated\"\n---\nDEMO-123 and DEMO-124")
            refreshed = store.board(db)[0]["cards"][0]
            self.assertEqual(refreshed["devlog_notes"][0]["title"], "Updated")
            db.close()
        finally:
            store.DB_PATH = original_db_path
            store.DEVLOG_ROOT = original_devlog_root

    def test_note_api_returns_content_and_rejects_root_files(self):
        self.write_note("projects/vend/notes/api.md", "# API note")
        original_root = store.DEVLOG_ROOT
        original_db_path = store.DB_PATH
        original_db = server.DB
        store.DEVLOG_ROOT = self.devlog_root
        store.DB_PATH = self.devlog_root / "note-api.db"
        connection = store.connect()
        server.DB = connection
        http = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{http.server_port}"
            with urlopen(f"{base}/api/devlog-note?path={quote('vend/notes/api.md')}") as response:
                self.assertEqual(json.load(response)["content"], "# API note")
            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base}/api/devlog-note?path={quote('vend/index.md')}")
            self.assertEqual(raised.exception.code, 404)
        finally:
            http.shutdown()
            http.server_close()
            connection.close()
            server.DB = original_db
            store.DEVLOG_ROOT = original_root
            store.DB_PATH = original_db_path

    def test_board_api_rescans_devlog_on_each_refresh(self):
        self.write_note("projects/vend/notes/first.md", "DEMO-123 report")
        original_root = store.DEVLOG_ROOT
        original_db_path = store.DB_PATH
        original_db = server.DB
        store.DEVLOG_ROOT = self.devlog_root
        store.DB_PATH = self.devlog_root / "board.db"
        connection = store.connect()
        column_id = store.add_column(connection, "Ongoing")
        store.add_card(connection, column_id, "DEMO-123 / DEMO-124: Example")
        server.DB = connection
        http = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{http.server_port}/api/devlog-refresh"
            request = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request) as response:
                first_board = json.load(response)["board"]
                first = next(card["devlog_notes"] for column in first_board for card in column["cards"])
            self.assertEqual([note["path"] for note in first], ["projects/vend/notes/first.md"])

            self.write_note("projects/vend/bugs/second.md", "DEMO-124 follow-up")
            request = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request) as response:
                refreshed_board = json.load(response)["board"]
                refreshed = next(card["devlog_notes"] for column in refreshed_board for card in column["cards"])
            self.assertEqual(
                {note["path"] for note in refreshed},
                {"projects/vend/notes/first.md", "projects/vend/bugs/second.md"},
            )
        finally:
            http.shutdown()
            http.server_close()
            connection.close()
            server.DB = original_db
            store.DEVLOG_ROOT = original_root
            store.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
