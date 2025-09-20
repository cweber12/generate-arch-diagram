# app/tools/mermaid.py
import os, json, re
from pathlib import Path
from collections import defaultdict, deque

APP_ROOT = Path(__file__).resolve().parents[1]
routes_path = APP_ROOT / "routes.json"
callgraph_path = APP_ROOT / "callgraph.json"

# Controls (can be set by env)
MODE = os.getenv("MERMAID_MODE", "api")         # "api" | "nhops" | "full"
MAX_HOPS = int(os.getenv("MAX_HOPS", "1"))
DIR = os.getenv("MERMAID_DIR", "TD")            # "TD" | "TB" | "LR" | "RL" | "BT"
LABEL_MODE = os.getenv("LABEL_MODE", "short")   # "short" | "full"
LABEL_DEPTH = int(os.getenv("LABEL_DEPTH", "2"))# how many trailing segments for "short"
WRAP_BY_DOT = os.getenv("WRAP_BY_DOT", "1") == "1"  # replace '.' with <br/> to wrap

def load_routes():
    if not routes_path.exists():
        return []
    with routes_path.open(encoding="utf-8-sig") as f:
        return json.load(f)

def load_callgraph():
    if not callgraph_path.exists():
        return {"edges": []}
    with callgraph_path.open(encoding="utf-8-sig") as f:
        return json.load(f)

_id_re = re.compile(r'[^A-Za-z0-9_]')
def safe_id(s: str) -> str:
    return _id_re.sub("_", s)

def shorten_label(qualified: str) -> str:
    if LABEL_MODE == "short":
        parts = qualified.split(".")
        if len(parts) > LABEL_DEPTH:
            qualified = ".".join(parts[-LABEL_DEPTH:])
    if WRAP_BY_DOT:
        # turn "a.b.c" into "a<br/>b<br/>c" so nodes are taller not wider
        return qualified.replace(".", "<br/>")
    return qualified

def esc_label(s: str) -> str:
    return s.replace('"', '\\"')

def fn_node(fn: str) -> str:
    return f"FN_{safe_id(fn)}"

def ep_node(method: str, path: str) -> str:
    return f"EP_{safe_id(method + '_' + path)}"

def main():
    routes = load_routes()
    cg = load_callgraph()
    edges = cg.get("edges", [])

    out_edges = defaultdict(set)
    for e in edges:
        out_edges[e["caller"]].add(e["callee"])

    lines = []
    lines += [
        f"flowchart {DIR}",
        "classDef endpoint fill:#eef,stroke:#88a,stroke-width:1px;",
        "classDef handler  fill:#efe,stroke:#6a6,stroke-width:1px;",
        "classDef data     fill:#fee,stroke:#c88,stroke-width:1px;",
        "classDef tag      fill:#eee,stroke:#bbb,stroke-dasharray: 3 3;",
        "classDef dep      fill:#fff4cc,stroke:#c7a84f,stroke-width:1px;",
        "",
        "%% Tag nodes"
    ]

    # tags
    tag_nodes = {}
    for r in routes:
        for t in (r.get("tags") or []):
            if t not in tag_nodes:
                tn = f"TAG_{safe_id(t)}"
                lines.append(f'{tn}["tag: {esc_label(t)}"]:::tag')
                tag_nodes[t] = tn

    # endpoints + handlers
    handler_nodes = set()
    for r in routes:
        path = r["path"]
        for m in r["methods"]:
            ep = ep_node(m, path)
            handler = r["endpoint"]
            hnode = fn_node(handler)
            handler_nodes.add(handler)

            ep_label = f"{m} {path}"
            h_label = shorten_label(handler)

            lines.append(f'{ep}["{esc_label(ep_label)}"]:::endpoint')
            lines.append(f'{hnode}["{esc_label(h_label)}"]:::handler')
            lines.append(f'{ep} --> {hnode}')

            # tag association
            for t in (r.get("tags") or []):
                lines.append(f'{ep} --- {tag_nodes[t]}')

    # callgraph overlay
    def add_edge(u, v):
        lines.append(f'{fn_node(u)} --> {fn_node(v)}')

    if MODE == "api":
        lines.append("\n%% Call graph from handlers (1 hop)")
        for h in handler_nodes:
            for d in out_edges.get(h, []):
                add_edge(h, d)
    elif MODE == "nhops":
        lines.append(f"\n%% Call graph from handlers ({MAX_HOPS} hops)")
        seen = set()
        q = deque()
        for h in handler_nodes:
            q.append((h, 0))
        while q:
            cur, dist = q.popleft()
            if dist >= MAX_HOPS:
                continue
            for nxt in out_edges.get(cur, []):
                add_edge(cur, nxt)
                key = (nxt, dist + 1)
                if key not in seen:
                    seen.add(key)
                    q.append((nxt, dist + 1))
    else:  # full
        lines.append("\n%% Full callgraph edges")
        for e in edges:
            add_edge(e["caller"], e["callee"])

    print("\n".join(lines))

if __name__ == "__main__":
    main()
