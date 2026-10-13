"""Kanban web server (stdlib only). Run: python3 -m kanban.server [port]"""
import json, sys, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from . import store as s
from .config import load_config

STATIC = Path(__file__).parent / "static"
LOCK = threading.Lock()
DB = s.connect()
FAVICON = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#2a2e37"/>'
           b'<rect x="9" y="10" width="14" height="38" rx="3" fill="#6aa9ff"/><rect x="25" y="10" width="14" height="26" rx="3" fill="#8bd48b"/>'
           b'<rect x="41" y="10" width="14" height="44" rx="3" fill="#ffb454"/></svg>')


class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, code, data, ctype="application/json"):
        b = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/api/config":
            config = load_config()
            return self.send(200, {"board_name": config["board_name"]})
        if self.path == "/api/board":
            with LOCK:
                return self.send(200, s.board(DB))
        if self.path.startswith("/api/devlog-note?"):
            note_path = parse_qs(urlsplit(self.path).query).get("path", [""])[0]
            note = s.read_devlog_note(note_path)
            if note is None:
                return self.send(404, {"error": "note not found"})
            return self.send(200, note)
        if self.path == "/api/export.md":
            with LOCK:
                return self.send(200, s.export_md(DB).encode(), "text/markdown")
        if self.path.startswith("/api/cards/") and self.path.endswith("/history"):
            with LOCK:
                return self.send(200, s.history(DB, int(self.path.split("/")[3])))
        if self.path in ("/favicon.ico", "/favicon.svg"):
            return self.send(200, FAVICON, "image/svg+xml")
        if self.path in ("/", "/index.html"):
            return self.send(200, (STATIC / "index.html").read_bytes(), "text/html")
        static_path = (STATIC / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
        try:
            static_path.relative_to(STATIC.resolve())
        except ValueError:
            return self.send(404, {"error": "not found"})
        if static_path.is_file():
            content_type = "application/javascript" if static_path.suffix == ".js" else "text/plain"
            return self.send(200, static_path.read_bytes(), content_type)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if urlsplit(self.path).path == "/api/devlog-refresh":
            try:
                with LOCK:
                    note_index = s.devlog_note_index()
                    board = s.board(DB, note_index)
                return self.send(200, {"board": board, "scanned_at": s.now()})
            except OSError:
                return self.send(500, {"error": "devlog scan failed"})
        self.handle_m("POST")

    def route(self, method):
        p = self.path.strip("/").split("/")  # api, cards|columns, [id], [move]
        d = self.body() if method in ("POST", "PATCH") else {}
        if p[:2] == ["api", "cards"]:
            if method == "POST" and len(p) == 2:
                return {"id": s.add_card(DB, d["column_id"], d["title"], d.get("content", ""), d.get("marker", ""), d.get("tags", ()))}
            cid = int(p[2])
            if method == "POST" and p[3:] == ["move"]:
                s.move_card(DB, cid, d["column_id"], d["index"])
                return {}
            if method == "PATCH":
                s.update_card(DB, cid, **{k: d[k] for k in s.EDITABLE if k in d})
                return {}
            if method == "DELETE":
                s.delete_card(DB, cid)
                return {}
        if p[:2] == ["api", "columns"]:
            if method == "POST" and len(p) == 2:
                return {"id": s.add_column(DB, d["name"])}
            colid = int(p[2])
            if method == "PATCH":
                s.update_column(DB, colid, **{k: d[k] for k in ("name", "collapsed") if k in d})
                return {}
            if method == "DELETE":
                s.delete_column(DB, colid)
                return {}
        raise KeyError

    def handle_m(self, m):
        try:
            with LOCK:
                r = self.route(m)
            self.send(200, r)
        except (KeyError, IndexError, ValueError):
            self.send(400, {"error": "bad request"})

    def do_PATCH(self): self.handle_m("PATCH")
    def do_DELETE(self): self.handle_m("DELETE")


if __name__ == "__main__":
    config = load_config()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(config["port"])
    print(f"{config['board_name']} on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
