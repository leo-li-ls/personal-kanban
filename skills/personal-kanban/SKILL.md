---
name: personal-kanban
description: Operate the local Personal Kanban board configured for the current project. Use whenever the user asks what they are working on, to list or search tasks, add/edit/move/complete/block/archive cards, check task history, export/import a board, or manage its local web UI. Read the project's config.json to locate its SQLite board and Devlog data; never assume a fixed user-specific path. Use this skill rather than editing the database directly.
---

# Personal Kanban Agent Skill

Use this skill to safely operate a Personal Kanban installation from its project directory. The board is a local SQLite database with a CLI and optional localhost web UI.

## Find the right board

1. Locate the Personal Kanban project root from the current working directory or ask the user which installation they mean if there are multiple.
2. Read its `README.md`, `AGENTS.md` when present, and `config.json`. The configuration is installation-specific and is intentionally not committed to Git.
3. Run every CLI command with the project root as the working directory:

   ```sh
   python3 -m kanban.cli show
   ```

4. Treat `<project-root>/data/kanban.db` as the source of truth. Never mutate it directly with SQLite or scripts when a CLI command exists.
5. If `config.json` or the database is missing, explain that initialization is required (`python3 install.py`) rather than creating a parallel board elsewhere.

The default columns are `Backlog`, `In Progress`, and `Done`, but users can rename, add, or remove columns. Always inspect `show` output and use the actual column names. CLI column matching is a case-insensitive substring, so use a sufficiently distinctive name.

## Common commands

Run from the project root:

```sh
python3 -m kanban.cli show [-a]                         # list cards; -a includes Done/Archive
python3 -m kanban.cli get <card-id>                     # inspect a card
python3 -m kanban.cli history <card-id>                 # review its event history
python3 -m kanban.cli add "<column>" "<title>" "<content>" '{"marker":"🔥","tags":["work"]}'
python3 -m kanban.cli move <card-id> "<column>"         # move card to the top of a column
python3 -m kanban.cli done <card-id>                    # mark done and move to Done
python3 -m kanban.cli edit <card-id> '<json-fields>'    # update selected card fields
python3 -m kanban.cli export                            # export Obsidian Kanban Markdown
python3 -m kanban.cli import <markdown-file>            # append imported columns/cards
```

The CLI has no search subcommand. Use the web UI's search box for interactive search, or inspect `show` output and filter the displayed text when an agent needs to find a card.

Editable fields are `marker`, `title`, `content`, `tags`, `done`, and `done_date`. Fetch the card with `get` before editing so you preserve fields the user did not ask to change. For example, to add a `blocked` tag, retain the existing tags and content, append a concise `BLOCKED: <reason>` note, and submit the updated values together.

## Task workflows

- **What am I working on / what should I do next?** Run `show`, identify active cards from the board's in-progress columns, and read their content with `get` when details matter. Report cards as stored; do not move them just to make the board look current.
- **Start work:** move the selected card to the actual in-progress column (commonly `In Progress`). Verify with `get` or `show` and report the resulting column and card ID.
- **Finish work:** if there is a column whose name matches `Done`, use `done <id>`, then verify that the card is marked done and in that column. If the completion column has a different name, move the card to that actual column and set `done: true` with `edit`; verify both values. Only set a completion date when the user supplies or confirms it.
- **Block work:** preserve the card's existing content/tags, add the reason to content, and add a `blocked` tag. Verify the update.
- **Add work:** inspect the board first and look for duplicates by title or ticket/reference key. Keep titles concise; put links, context, and next steps in content. Add it to the requested or clearly appropriate column and report the new ID.
- **Edit or move:** resolve ambiguous references before modifying a card. Inspect current values first and confirm the result after the change.
- **History:** use `history <id>` for when and how a card changed; distinguish logged board events from estimates or external issue status.

## Safety and data integrity

- Ask before deleting a card or column. The CLI's `rm` deletes a card permanently; column deletion also deletes its cards.
- Ask before importing Markdown into a populated board. Import appends columns and cards and can create duplicates.
- Do not silently reconcile the kanban with an external tracker. If asked to compare, report the mismatch and let the user decide whether the card should move.
- After every mutation, verify the updated board/card before claiming success. Include card IDs in confirmations.
- Export a Markdown backup before user-requested bulk changes:

  ```sh
  python3 -m kanban.cli export > data/backup-YYYY-MM-DD.md
  ```

## Devlog integration

The web UI can link notes to cards when a Jira-style key (for example `TEAM-123`) in the card title matches one in a Devlog note. Read `devlog_root` from the project's `config.json`; do not guess a path and do not treat the cloned Devlog skill repository as the user's data.

Before querying, summarizing, or recording Devlog knowledge:

1. Confirm the configured data folder exists and read its `AGENTS.md`.
2. Follow the separately installed Devlog skill at <https://github.com/leo-li-ls/devlog> for archive, recall, query, and lint workflows.
3. Read notes only from the configured data folder, especially `projects/`; respect its privacy and scope rules.

If the skill is not installed or the configured data folder is missing/unreadable, tell the user what is missing. Continue with board operations that do not require Devlog context when possible.

## Web UI

Start from the project root with `./run.sh` and open <http://127.0.0.1:8765> (or the configured/overridden port). The app binds to localhost. Do not start another server if one is already running; check the port first. Ask before stopping or killing an existing process. To stop a server you started in the foreground, use `Ctrl-C` in that terminal.

The local HTTP API exposes `GET /api/board`, `GET /api/cards/<id>/history`, `GET /api/export.md`, plus card and column mutation endpoints. Use it only when the CLI is insufficient, send JSON with an HTTP client, and follow the same confirmation and verification rules. Avoid `curl -X` in environments that block it; Python `urllib` is a portable alternative.
