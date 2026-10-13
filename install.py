"""Interactive first-run setup for Personal Kanban."""

from pathlib import Path

from kanban.config import DEFAULTS, CONFIG_PATH, validate_devlog_root, write_config


def main() -> None:
    """Collect a board title and a verified, populated devlog data path."""
    print("Personal Kanban setup\n")
    print("Before continuing, install the devlog skill as described in README.md.")
    board_name = input(f"Board title [{DEFAULTS['board_name']}]: ").strip() or DEFAULTS["board_name"]

    candidates = [Path.home() / "devlog", Path.home() / "Documents" / "devlog"]
    suggested = next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])
    while True:
        raw_path = input(f"Path to your devlog DATA folder [{suggested}]: ").strip()
        devlog_root = Path(raw_path or suggested).expanduser()
        try:
            note_count = validate_devlog_root(devlog_root)
        except ValueError as error:
            print(f"Devlog check failed: {error}")
            print("Enter the root of your actual log data, not the cloned devlog skill repository.")
            continue
        print(f"Verified {devlog_root}: AGENTS.md, index.md and {note_count} readable Markdown note(s).")
        break

    write_config({
        "board_name": board_name,
        "devlog_root": str(devlog_root.resolve()),
        "port": DEFAULTS["port"],
    })
    print(f"\nConfiguration saved to {CONFIG_PATH}")
    print("Setup complete. Start the board with ./run.sh")


if __name__ == "__main__":
    main()
