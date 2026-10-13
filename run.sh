#!/bin/sh
# Start the configured kanban web UI (default port: 8765).
cd "$(dirname "$0")"
if [ "$#" -gt 0 ]; then
  exec python3 -m kanban.server "$1"
fi
exec python3 -m kanban.server
