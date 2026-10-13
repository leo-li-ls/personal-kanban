# Personal Kanban

A small local-first kanban board with a SQLite-backed CLI and web UI. The board title and your Devlog data location are configurable. Data stays in this project directory and is not included in this shareable application copy.

## Important: install the Devlog skill first

Before setting up this board, install the **Devlog skill** from [leo-li-ls/devlog](https://github.com/leo-li-ls/devlog). The agent integration relies on the skill's workflow and structure, and the board reads from your separate Devlog **data** folder.

For OpenCode, clone the repository and install its skill file:

```sh
git clone https://github.com/leo-li-ls/devlog.git ~/Code/devlog-skill
mkdir -p ~/.config/opencode/skills/devlog
cp ~/Code/devlog-skill/SKILL.md ~/.config/opencode/skills/devlog/SKILL.md
```

Restart OpenCode (or start a new session) so it discovers the skill. For other AI agents, follow their skill-installation instructions and install the same `SKILL.md` before asking the agent to use the board.

## Install the Personal Kanban agent skill

This repository includes a reusable board-operation skill at `skills/personal-kanban/SKILL.md`. Install it into your agent's user-level skills directory so it can find and operate the correct board from its project directory. The skill reads the current installation's `config.json`; it does not contain a hard-coded home directory.

### OpenCode

```sh
mkdir -p ~/.config/opencode/skills/personal-kanban
cp skills/personal-kanban/SKILL.md ~/.config/opencode/skills/personal-kanban/SKILL.md
```

Start a new OpenCode session to load the skill. The separate Devlog skill above is still required for Devlog workflows.

### Claude Code

```sh
mkdir -p ~/.claude/skills/personal-kanban
cp skills/personal-kanban/SKILL.md ~/.claude/skills/personal-kanban/SKILL.md
```

Restart Claude Code or start a new session. For other agents, copy the skill folder into their documented user-level skills location and start a new session.

After installation, open the `personal-kanban` project as the agent's working directory and ask it to inspect your board. The skill instructs the agent to read `config.json`, use the project's CLI, verify changes, and consult the configured Devlog data only via the separately installed Devlog skill.

The skill repository is **not** your personal log. Create/use your separate Devlog data folder according to the repository's README. The data folder must contain readable `AGENTS.md`, `index.md`, and a populated `projects/` directory with Markdown notes. Keep private project notes in a private location.

## Install and initialize

Requirements: Python 3.10+; no third-party Python packages are needed.

```sh
cd ~/Code/personal-kanban
python3 install.py
```

The installer asks for the board title and Devlog data path. It suggests common locations such as `~/devlog`, but asks you to confirm the path. It then checks that `AGENTS.md`, `index.md`, and at least one readable Markdown file under `projects/` are present. If validation fails, enter the root folder of the actual log data (not the skill checkout). The values are saved in ignored `config.json`:

```json
{
  "board_name": "My Work",
  "devlog_root": "/Users/you/devlog",
  "port": 8765
}
```

The SQLite database is created at `data/kanban.db` on first use. `config.example.json` documents the available fields; the installer's `config.json` is ignored by Git. Back up `data/` to preserve your board. Do not share `config.json` or `data/` if they contain private information.

## Start the web server

Run in a terminal:

```sh
cd ~/Code/personal-kanban
./run.sh
```

Open <http://127.0.0.1:8765>. The server binds to localhost only. Use `./run.sh 9000` to choose a different port for that run. Press `Ctrl-C` to stop it.

To run in the background for the current login session:

```sh
cd ~/Code/personal-kanban
nohup ./run.sh > ~/Library/Logs/personal-kanban.log 2>&1 &
```

Check the log at `~/Library/Logs/personal-kanban.log`; stop it by locating the process with `lsof -i :8765` and stopping that process when you are ready.

### Start automatically at macOS login (LaunchAgent)

Create `~/Library/LaunchAgents/com.personal-kanban.server.plist`, replacing `/Users/YOU` with your home directory:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.personal-kanban.server</string>
  <key>ProgramArguments</key><array>
    <string>/Users/YOU/Code/personal-kanban/run.sh</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/YOU/Code/personal-kanban</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/YOU/Library/Logs/personal-kanban.log</string>
  <key>StandardErrorPath</key><string>/Users/YOU/Library/Logs/personal-kanban-error.log</string>
</dict></plist>
</plist>
```

Load/start it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal-kanban.server.plist`. To stop and disable it, run `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.personal-kanban.server.plist`. The server is private to this Mac's localhost; this is not a remote hosting setup.

## Use from an AI agent

Install both the Devlog skill and Personal Kanban skill (see above), then open this project as the agent's working directory. The agent should read `README.md`, `AGENTS.md`, and `config.json` before using the board; `config.json` identifies both the board title and the actual Devlog data root. The kanban skill covers safe CLI and web API workflows, while the Devlog skill covers recording and querying project context.

The board CLI uses the current project directory:

```sh
python3 -m kanban.cli show [-a]                  # list cards; -a includes Done/Archive
python3 -m kanban.cli get <card-id>               # card details
python3 -m kanban.cli history <card-id>           # card event history
python3 -m kanban.cli add Backlog "Task title" "Notes or links"
python3 -m kanban.cli move <card-id> "In Progress"
python3 -m kanban.cli done <card-id>
python3 -m kanban.cli edit <card-id> '{"tags":["work"]}'
python3 -m kanban.cli export                         # export Obsidian kanban Markdown
python3 -m kanban.cli import path/to/board.md        # appends imported columns/cards
```

Column names are user-defined; commands match a column by case-insensitive substring. Check existing cards before adding duplicates. Ask before deleting cards/columns or importing into an already-populated board. Import always appends the Markdown columns/cards; on a fresh board, remove any unused default columns in the UI if you do not need them. When marking work done, verify the updated card afterward.

Recommended agent prompts after opening this directory:

> Read `AGENTS.md`, `README.md`, and `config.json`, then tell me which board and Devlog data folder are configured.

> Show my active kanban tasks and check related project context in my Devlog.

> Add this task to Backlog, check for duplicates first, and include these links and next steps: …

> I started card `<id>`; move it to In Progress and confirm the new state.

Project-level agent instructions are in `AGENTS.md`; they define safe board operations and explain how to use the configured Devlog data together with the installed skill.

The web UI supports card editing, drag/drop, search, tags, history, and Markdown export. It scans the configured Devlog data on refresh and links notes whose Jira keys appear in card titles. Agents may also use the local JSON API (`GET /api/board`, `GET /api/cards/<id>/history`, `GET /api/export.md`, and the card/column `POST`, `PATCH`, and `DELETE` endpoints); use an HTTP client or Python `urllib`.

## Data and privacy

- `data/kanban.db` is the source of truth for cards and history.
- `config.json` points to the actual Devlog data and is machine-specific.
- Devlog notes are read from `projects/` and are not copied into this repository.
- Do not publish your database, configuration, or Devlog data unless you have reviewed them for private information.
