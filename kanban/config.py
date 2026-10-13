"""Load and validate the personal-kanban application configuration."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DEFAULTS = {
    "board_name": "Personal Kanban",
    "devlog_root": str(Path.home() / "devlog"),
    "port": 8765,
}


def load_config(path: Path | None = None) -> dict:
    """Read settings, filling absent keys with safe defaults."""
    path = path or CONFIG_PATH
    if not path.exists():
        return DEFAULTS.copy()
    with path.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    return {**DEFAULTS, **config}


def write_config(config: dict, path: Path | None = None) -> None:
    """Persist application settings as formatted JSON."""
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, ensure_ascii=False, indent=2)
        config_file.write("\n")


def validate_devlog_root(root: Path | str) -> int:
    """Verify that a populated devlog can be read and return its note count."""
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Devlog directory does not exist: {path}")
    for required_file in ("AGENTS.md", "index.md"):
        candidate = path / required_file
        if not candidate.is_file():
            raise ValueError(f"Missing {required_file} in {path}; this must be your devlog data folder, not the skill repository")
        try:
            candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError(f"Cannot read {candidate}: {error}") from error
    projects = path / "projects"
    if not projects.is_dir():
        raise ValueError(f"Missing projects/ in {path}; create it and add your project notes first")
    notes = []
    for note in projects.rglob("*.md"):
        try:
            note.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError(f"Cannot read {note}: {error}") from error
        notes.append(note)
    if not notes:
        raise ValueError(f"No Markdown data found under {projects}; add a project note before setup")
    return len(notes)
