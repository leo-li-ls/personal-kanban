"""Personal Kanban CLI. Usage: python3 -m kanban.cli <cmd> ..."""
import sys, json
from . import store as s

def main(a):
    c = s.connect(); cmd = a[0] if a else "show"
    if cmd == "import": s.import_md(c, a[1])
    elif cmd == "export": print(s.export_md(c))
    elif cmd == "show":
        for col in s.board(c):
            if col["name"].lower() in ("done", "archive") and "-a" not in a:
                print(f"## {col['name']} ({len(col['cards'])} cards, hidden; use -a)"); continue
            print(f"## {col['name']} [{col['id']}] ({len(col['cards'])})")
            for k in col["cards"]: print(f"  [{k['id']}] {'x' if k['done'] else ' '} {k['marker']} {k['title']}  {' '.join('#'+x for x in k['tags'])}")
    elif cmd == "add": x = json.loads(a[4]) if len(a) > 4 else {}; print(s.add_card(c, s.find_column(c, a[1]), a[2], a[3] if len(a) > 3 else "", x.get("marker", ""), x.get("tags", ())))
    elif cmd == "move": s.move_card(c, int(a[1]), s.find_column(c, a[2]), 0)
    elif cmd == "done": s.update_card(c, int(a[1]), done=True); s.move_card(c, int(a[1]), s.find_column(c, "done"), 0)
    elif cmd == "edit": s.update_card(c, int(a[1]), **json.loads(a[2]))
    elif cmd == "get": print(json.dumps(next((k for col in s.board(c) for k in col["cards"] if k["id"] == int(a[1])), None), ensure_ascii=False, indent=1))
    elif cmd == "history":
        for e in s.history(c, int(a[1])): print(e["at"], e["type"], e["from_col"] or "-", "->", e["to_col"] or "-", e["detail"])
    elif cmd == "rm": s.delete_card(c, int(a[1]))
    else: print("cmds: show [-a] | add <col> <title> [content] [extras-json: marker,tags] | move <id> <col> | done <id> | edit <id> '<json>' | get <id> | history <id> | rm <id> | export | import <md>")
main(sys.argv[1:])
