"""SQLite store for the kanban board + import/export of Obsidian-kanban markdown.

Card fields (each stored and editable separately):
  marker    emoji priority/type, e.g. 1️⃣ 🔥 🐛 🔥🐛 (free text, emoji only)
  title     plain title (no emoji prefix, no done date)
  content   free-form body (links, notes), without the tag line
  tags      JSON list of tag names (no '#')
  done      0/1
  done_date YYYY-MM-DD or ''
"""
import json, re, sqlite3, time
from pathlib import Path
from .config import load_config

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "kanban.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS columns(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, position REAL NOT NULL,
  collapsed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS cards(
  id INTEGER PRIMARY KEY, column_id INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
  position REAL NOT NULL, marker TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
  done INTEGER NOT NULL DEFAULT 0, done_date TEXT NOT NULL DEFAULT '',
  devlog_notes TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_cards_col ON cards(column_id, position);
CREATE TABLE IF NOT EXISTS card_events(
  id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  at TEXT NOT NULL, type TEXT NOT NULL,          -- created | moved | done | undone | edited
  from_col TEXT, to_col TEXT,                    -- column NAMES (snapshot, survive renames/deletes)
  detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_events_card ON card_events(card_id, at);
"""

EMOJI = (r"(?:[0-9#*]\uFE0F?\u20E3|[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF"
         r"\u23E9-\u23FF\u2190-\u21FF\u25A0-\u25FF]\uFE0F?)")
MARKER_RE = re.compile(rf"^(?:{EMOJI}|\s)+")
DONE_RE = re.compile(r"\s*✅\s*(\d{4}-\d{2}-\d{2})\s*$")
TAGLINE_RE = re.compile(r"^\s*(#[\w\-]+\s*)+$")
JIRA_KEY_RE = re.compile(r"(?<![A-Z0-9-])([A-Z][A-Z0-9]+-\d+)(?![A-Z0-9-])")
DEVLOG_ROOT = Path(load_config()["devlog_root"]).expanduser()


def _frontmatter_title(text, fallback):
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.S)
    if match:
        title = re.search(r'^title:\s*[\"\']?(.*?)[\"\']?\s*$', match.group(1), re.M)
        if title and title.group(1).strip():
            return title.group(1).strip().strip('\"\'')
    return fallback


def find_devlog_notes(title, devlog_root=None):
    """Return devlog notes in project subfolders matching Jira keys from a card title."""
    keys = list(dict.fromkeys(JIRA_KEY_RE.findall(title)))
    index = devlog_note_index(devlog_root)
    notes_by_path = {}
    for key in keys:
        for note in index.get(key, []):
            notes_by_path.setdefault(note["path"], note)
    return list(notes_by_path.values())


def devlog_note_index(devlog_root=None):
    """Index Markdown notes under project subfolders by their Jira keys."""
    root = Path(devlog_root) if devlog_root is not None else DEVLOG_ROOT
    projects = root / "projects"
    index = {}
    if not projects.is_dir():
        return index
    for project in sorted(path for path in projects.iterdir() if path.is_dir()):
        for path in sorted(project.rglob("*.md")):
            if path.parent == project and path.name in {"index.md", "log.md"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            keys = list(dict.fromkeys(JIRA_KEY_RE.findall(text)))
            if not keys:
                continue
            note = {
                "path": path.relative_to(root).as_posix(),
                "title": _frontmatter_title(text, path.stem.replace("-", " ")),
                "jira_keys": keys,
            }
            for key in keys:
                index.setdefault(key, []).append(note)
    return index


def read_devlog_note(note_path, devlog_root=None):
    """Read a Markdown note by its project-relative path, rejecting root files and traversal."""
    root = Path(devlog_root) if devlog_root is not None else DEVLOG_ROOT
    projects = (root / "projects").resolve()
    parts = Path(note_path).parts
    if any(part in {"..", ""} for part in parts):
        return None
    if parts and parts[0] == "projects":
        parts = parts[1:]
    if not parts:
        return None
    candidate = (projects / Path(*parts)).resolve()
    try:
        relative = candidate.relative_to(projects)
    except ValueError:
        return None
    if not relative.parts or relative.suffix.lower() != ".md":
        return None
    project_root = projects / relative.parts[0]
    if candidate.parent == project_root and candidate.name in {"index.md", "log.md"}:
        return None
    try:
        text = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    return {
        "path": relative.as_posix(),
        "title": _frontmatter_title(text, candidate.stem.replace("-", " ")),
        "content": text,
    }


def now(): return time.strftime("%Y-%m-%dT%H:%M:%S")


def split_card(title, body):
    """Split a legacy 'emoji title ✅ date' + 'body #tags' into separate fields."""
    done_date = ""
    m = DONE_RE.search(title)
    if m: done_date = m.group(1); title = title[:m.start()]
    marker = ""
    m = MARKER_RE.match(title)
    if m: marker = re.sub(r"\s+", "", m.group(0)); title = title[m.end():]
    tags, keep = [], []
    for line in body.split("\n"):
        if TAGLINE_RE.match(line): tags += re.findall(r"#([\w\-]+)", line)
        else: keep.append(line)
    content = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
    return dict(marker=marker, title=title.strip(), content=content,
                tags=list(dict.fromkeys(tags)), done_date=done_date)


def norm_tags(t):
    if isinstance(t, str): t = re.split(r"[,\s]+", t)
    return list(dict.fromkeys(x.lstrip("#") for x in t if x.lstrip("#")))


def log(c, cid, type, frm=None, to=None, detail="", at=None):
    c.execute("INSERT INTO card_events(card_id,at,type,from_col,to_col,detail) VALUES(?,?,?,?,?,?)",
              (cid, at or now(), type, frm, to, detail))


def colname(c, colid):
    r = c.execute("SELECT name FROM columns WHERE id=?", (colid,)).fetchone()
    return r["name"] if r else None


def history(c, cid):
    return [dict(r) for r in c.execute("SELECT at,type,from_col,to_col,detail FROM card_events WHERE card_id=? ORDER BY at,id", (cid,))]


def backfill_events(c):
    # cards without any event get a 'created' event at created_at in their current column
    for r in c.execute("SELECT k.id,k.created_at,k.done,k.done_date,col.name FROM cards k JOIN columns col ON col.id=k.column_id "
                       "WHERE NOT EXISTS (SELECT 1 FROM card_events e WHERE e.card_id=k.id)").fetchall():
        log(c, r["id"], "created", None, r["name"], "imported from markdown" , r["created_at"])
    c.commit()


def migrate(c):
    cols = {r["name"] for r in c.execute("PRAGMA table_info(cards)")}
    if "body" in cols and "content" not in cols:
        c.execute("ALTER TABLE cards RENAME COLUMN body TO content")
        c.execute("ALTER TABLE cards ADD COLUMN marker TEXT NOT NULL DEFAULT ''")
        c.execute("ALTER TABLE cards ADD COLUMN done_date TEXT NOT NULL DEFAULT ''")
        for r in c.execute("SELECT id,title,content FROM cards").fetchall():
            f = split_card(r["title"], r["content"])
            c.execute("UPDATE cards SET marker=?,title=?,content=?,tags=?,done_date=? WHERE id=?",
                      (f["marker"], f["title"], f["content"], json.dumps(f["tags"], ensure_ascii=False),
                       f["done_date"], r["id"]))
        c.commit()
    cols = {r["name"] for r in c.execute("PRAGMA table_info(cards)")}
    if "devlog_notes" not in cols:
        c.execute("ALTER TABLE cards ADD COLUMN devlog_notes TEXT NOT NULL DEFAULT '[]'")
        c.commit()


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA)
    migrate(c)
    if c.execute("SELECT COUNT(*) FROM columns").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO columns(name,position) VALUES(?,?)",
            [("Backlog", 0), ("In Progress", 1), ("Done", 2)],
        )
        c.commit()
    backfill_events(c)
    return c


def _card(r):
    d = dict(r); d["tags"] = json.loads(d["tags"]); d["done"] = bool(d["done"])
    d["devlog_notes"] = json.loads(d.get("devlog_notes", "[]"))
    return d


def board(c, note_index=None):
    cols = []
    if note_index is None:
        note_index = devlog_note_index()
    for col in c.execute("SELECT * FROM columns ORDER BY position"):
        d = dict(col); d["collapsed"] = bool(d["collapsed"])
        d["cards"] = [_card(r) for r in c.execute(
            "SELECT * FROM cards WHERE column_id=? ORDER BY position", (col["id"],))]
        for card in d["cards"]:
            keys = list(dict.fromkeys(JIRA_KEY_RE.findall(card["title"])))
            notes_by_path = {}
            for key in keys:
                for note in note_index.get(key, []):
                    notes_by_path.setdefault(note["path"], note)
            card["devlog_notes"] = list(notes_by_path.values())
            encoded = json.dumps(card["devlog_notes"], ensure_ascii=False)
            c.execute("UPDATE cards SET devlog_notes=? WHERE id=? AND devlog_notes!=?",
                      (encoded, card["id"], encoded))
        cols.append(d)
    c.commit()
    return cols


def add_card(c, column_id, title, content="", marker="", tags=(), done=False, done_date="", top=True):
    f = "MIN(position)-1" if top else "MAX(position)+1"
    pos = c.execute(f"SELECT COALESCE({f},0) FROM cards WHERE column_id=?", (column_id,)).fetchone()[0]
    t = now()
    cur = c.execute("INSERT INTO cards(column_id,position,marker,title,content,tags,done,done_date,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (column_id, pos, marker, title, content, json.dumps(norm_tags(tags), ensure_ascii=False),
                     int(done), done_date, t, t))
    log(c, cur.lastrowid, "created", None, colname(c, column_id), at=t)
    c.commit(); return cur.lastrowid


EDITABLE = ("marker", "title", "content", "tags", "done", "done_date")


def update_card(c, cid, **f):
    old = c.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
    if not old: return False
    sets, vals, changed, flip = [], [], [], None
    for k in EDITABLE:
        if k not in f: continue
        v = f[k]
        if k == "tags": v = json.dumps(norm_tags(v), ensure_ascii=False)
        elif k == "done": v = int(bool(v))
        if v == old[k]: continue
        sets.append(f"{k}=?"); vals.append(v)
        if k == "done": flip = "done" if v else "undone"
        else: changed.append(k)
    if sets:
        t = now()
        c.execute(f"UPDATE cards SET {','.join(sets)},updated_at=? WHERE id=?", (*vals, t, cid))
        col = colname(c, old["column_id"])
        if flip: log(c, cid, flip, col, col, at=t)
        if changed: log(c, cid, "edited", col, col, ", ".join(changed), at=t)
        c.commit()
    return True


def move_card(c, cid, column_id, index):
    others = [r["position"] for r in c.execute(
        "SELECT position FROM cards WHERE column_id=? AND id!=? ORDER BY position", (column_id, cid))]
    index = max(0, min(index, len(others)))
    if not others: pos = 0.0
    elif index == 0: pos = others[0] - 1
    elif index == len(others): pos = others[-1] + 1
    else: pos = (others[index - 1] + others[index]) / 2
    old = c.execute("SELECT column_id FROM cards WHERE id=?", (cid,)).fetchone()
    t = now()
    c.execute("UPDATE cards SET column_id=?,position=?,updated_at=? WHERE id=?", (column_id, pos, t, cid))
    if old and old["column_id"] != column_id:
        log(c, cid, "moved", colname(c, old["column_id"]), colname(c, column_id), at=t)
    c.commit()


def delete_card(c, cid):
    c.execute("DELETE FROM cards WHERE id=?", (cid,)); c.commit()


def add_column(c, name):
    pos = c.execute("SELECT COALESCE(MAX(position)+1,0) FROM columns").fetchone()[0]
    cur = c.execute("INSERT INTO columns(name,position) VALUES(?,?)", (name, pos)); c.commit(); return cur.lastrowid


def update_column(c, colid, **f):
    if "name" in f: c.execute("UPDATE columns SET name=? WHERE id=?", (f["name"], colid))
    if "collapsed" in f: c.execute("UPDATE columns SET collapsed=? WHERE id=?", (int(f["collapsed"]), colid))
    c.commit()


def delete_column(c, colid):
    c.execute("DELETE FROM columns WHERE id=?", (colid,)); c.commit()


def find_column(c, name):
    r = c.execute("SELECT id FROM columns WHERE lower(name) LIKE ?", (f"%{name.lower()}%",)).fetchone()
    return r["id"] if r else None


# ---------- markdown (Obsidian kanban plugin) ----------
def import_md(c, path):
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)
    text = text.split("%% kanban:settings")[0]
    col = None; card = None

    def flush():
        nonlocal card
        if card and col:
            body = "\n".join(l[1:] if l.startswith("\t") else l for l in card["lines"]).strip("\n")
            f = split_card(card["title"], body)
            add_card(c, col, f["title"], f["content"], f["marker"], f["tags"], card["done"], f["done_date"], top=False)
        card = None
    for line in text.split("\n"):
        m = re.match(r"^## (.*)$", line)
        if m: flush(); col = add_column(c, m.group(1).strip()); continue
        m = re.match(r"^- \[([ xX])\] ?(.*)$", line)
        if m: flush(); card = {"done": m.group(1) != " ", "title": m.group(2).strip(), "lines": []}; continue
        if card is not None and line.strip() != "***": card["lines"].append(line)
    flush(); c.commit()


def export_md(c):
    out = ["---", "", "kanban-plugin: board", "", "---", ""]
    for col in board(c):
        out += [f"## {col['name']}", ""]
        for k in col["cards"]:
            t = (k["marker"] + " " if k["marker"] else "") + k["title"]
            if k["done_date"]: t += f" ✅ {k['done_date']}"
            out.append(f"- [{'x' if k['done'] else ' '}] {t}")
            body = k["content"]
            if k["tags"]: body = (body + "\n\n" if body else "") + " ".join("#" + x for x in k["tags"])
            if body:
                out.append("\t"); out += ["\t" + l if l else "\t" for l in body.split("\n")]
        out += ["", ""]
    out += ["%% kanban:settings", "```", '{"kanban-plugin":"board"}', "```", "%%", ""]
    return "\n".join(out)
