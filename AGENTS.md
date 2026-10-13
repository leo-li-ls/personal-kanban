# AI agent instructions

## Setup and context

- Before using the board, read `README.md` and `config.json`.
- `config.json` contains the user-configured board title and the absolute path to the separate Devlog **data** folder. Read that folder's `AGENTS.md` before querying or recording Devlog information.
- The reusable Devlog skill must be installed in the agent first: https://github.com/leo-li-ls/devlog
- Never assume the skill checkout contains user notes. Use only the configured data folder and its `projects/` subfolders.
- Run `python3 -m kanban.cli ...` with this project as the working directory. `data/kanban.db` is the board's source of truth; do not edit it directly.

## Board workflow

- Use `show` to inspect the board and `get <id>` before editing an existing card.
- Check for duplicate cards before adding a task. Use the actual column names shown by `show` (a case-insensitive substring is accepted).
- Use `move <id> "In Progress"` when work starts and `done <id>` when it is completed. Verify the resulting card with `get` or `show` after mutations.
- Keep titles concise. Put links, context, and next steps in content; use tags for useful categories.
- Ask before deleting cards/columns or importing Markdown into a populated board. Import appends content.
- For project context, follow the Devlog skill and the configured Devlog's `AGENTS.md`; do not invent undocumented decisions or status.
- The web UI is available at `http://127.0.0.1:<port>` after starting `./run.sh`. Keep the server on localhost unless the user explicitly requests a different network deployment.
