# app/main.py
from fastapi import FastAPI, HTTPException, Depends, Security, UploadFile, File, Form
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import os, hashlib, secrets, tempfile, subprocess, zipfile, io, shutil

# Load .env if present (API_KEY_SHA256, optional MMDC_PATH)
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

app = FastAPI(title="Architecture Diagram Service", version="0.4.0")

# --------------------------- Auth ---------------------------
API_KEY_HEADER = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)
API_KEY_SHA256 = os.getenv("API_KEY_SHA256")
if not API_KEY_SHA256:
    raise RuntimeError("Missing API_KEY_SHA256 env var")

def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    if not api_key:
        raise HTTPException(401, "Missing API key", headers={"WWW-Authenticate": "ApiKey"})
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    if not secrets.compare_digest(digest, API_KEY_SHA256):
        raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "ApiKey"})

# --------------------------- Paths --------------------------
APP_ROOT = Path(__file__).resolve().parent      # .../GenerateDiagram/app
TOOLS_DIR = APP_ROOT / "tools"                  # .../GenerateDiagram/app/tools
MERMAID_CONFIG = APP_ROOT / "mermaid.config.json"
PUPPETEER_CONFIG = APP_ROOT / "puppeteer.json"

# -------------------------- Helpers -------------------------
def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    try:
        res = subprocess.run(
            cmd, cwd=str(cwd), env=env, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return res.stdout
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            500,
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
        )

def _resolve_mmdc() -> str:
    """Find Mermaid CLI executable ('mmdc') across platforms."""
    custom = os.getenv("MMDC_PATH")
    candidates = [c for c in [custom, "mmdc", "mmdc.cmd"] if c]
    appdata = os.environ.get("APPDATA")  # Windows npm global bin
    if appdata:
        candidates.append(os.path.join(appdata, "npm", "mmdc.cmd"))
    for exe in candidates:
        try:
            subprocess.run([exe, "-V"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
            return exe
        except Exception:
            pass
    raise HTTPException(500, "Mermaid CLI not found. Install with: npm i -g @mermaid-js/mermaid-cli "
                             "or set MMDC_PATH to the full path of mmdc(.cmd).")

def _safe_unzip_to(zip_bytes: bytes, dest: Path) -> None:
    """Safely extract a .zip into dest, preventing path traversal."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.infolist():
            member_path = (dest / member.filename).resolve()
            if not str(member_path).startswith(str(dest.resolve())):
                continue
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
            else:
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(member_path, "wb") as out:
                    shutil.copyfileobj(src, out)

def _generate(
    project_dir: Path,
    package_dir: Optional[str],
    app_module: Optional[str],
    prefix: str,
    render: str,
    include_artifacts: bool,
    graph_mode: str,
    max_hops: int,
) -> dict:
    """Core generation logic used by both endpoints."""
    if not project_dir.exists():
        raise HTTPException(400, f"project_dir does not exist: {project_dir}")

    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = os.pathsep.join([
        str(APP_ROOT),        # allow app/tools imports
        str(project_dir),     # allow project imports (for app_module)
        base_env.get("PYTHONPATH", ""),
    ])

    # Resolve scan path
    if package_dir:
        scan_path = (project_dir / package_dir).resolve()
        if not scan_path.exists():
            raise HTTPException(400, f"package_dir '{package_dir}' not found under {project_dir}")
    else:
        maybe = project_dir / prefix
        scan_path = maybe if maybe.exists() else project_dir

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        routes_json = tmp_path / "routes.json"
        callgraph_json = tmp_path / "callgraph.json"

        # 1) Export routes (optional)
        if app_module:
            env = base_env.copy()
            env["APP_MODULE"] = app_module
            _run(["python", str(TOOLS_DIR / "export_routes.py"), "--out", str(routes_json)],
                 cwd=project_dir, env=env)
        else:
            routes_json.write_text("[]", encoding="utf-8")

        # 2) Build callgraph (always fresh)
        _run([
            "python", str(TOOLS_DIR / "callgraph_ast.py"),
            str(scan_path), "--out", str(callgraph_json), "--prefix", prefix
        ], cwd=project_dir, env=base_env)

        # 3) Mermaid: expects files in its cwd
        service_routes = APP_ROOT / "routes.json"
        service_callgraph = APP_ROOT / "callgraph.json"
        service_routes.write_text(routes_json.read_text(encoding="utf-8"), encoding="utf-8")
        service_callgraph.write_text(callgraph_json.read_text(encoding="utf-8"), encoding="utf-8")

        # mode/hops for mermaid.py
        mermaid_env = base_env.copy()
        mermaid_env["MERMAID_MODE"] = graph_mode
        mermaid_env["MAX_HOPS"] = str(max_hops)

        mermaid_txt = _run(["python", str(TOOLS_DIR / "mermaid.py")], cwd=APP_ROOT, env=mermaid_env)

        resp = {"mermaid": mermaid_txt}
        if include_artifacts:
            resp["artifacts"] = {
                "routes.json": service_routes.read_text(encoding="utf-8"),
                "callgraph.json": service_callgraph.read_text(encoding="utf-8"),
            }

        # 4) Optional SVG rendering with robust flags (if requested)
        if render == "svg":
            mmd = tmp_path / "diagram.mmd"
            svg = tmp_path / "diagram.svg"
            mmd.write_text(mermaid_txt, encoding="utf-8")
            mmdc = _resolve_mmdc()

            cmd = [mmdc, "-i", str(mmd), "-o", str(svg), "-b", "transparent", "--scale", "1"]
            if MERMAID_CONFIG.exists():
                cmd += ["--configFile", str(MERMAID_CONFIG)]
            if PUPPETEER_CONFIG.exists():
                cmd += ["--puppeteerConfigFile", str(PUPPETEER_CONFIG)]

            _run(cmd, cwd=APP_ROOT, env=base_env)
            resp.update({"svg": svg.read_text(encoding="utf-8"), "format": "svg"})

        return resp

# --------------------------- Models -------------------------
class DiagramRequest(BaseModel):
    project_dir: str = Field(..., description="Absolute path to the repo (server must see it)")
    package_dir: Optional[str] = Field(None, description="Subfolder to scan (e.g. 'app')")
    app_module: Optional[str] = Field(None, description="FastAPI app, e.g. 'app.main:app'")
    prefix: str = Field("app", description="Limit callgraph edges to this package prefix")
    render: str = Field("mermaid", pattern="^(mermaid|svg)$")
    include_artifacts: bool = True
    graph_mode: str = Field("api", pattern="^(api|nhops|full)$",
                            description="api=1 hop from handlers; nhops=N hops; full=all edges")
    max_hops: int = Field(1, ge=1, description="Used only when graph_mode='nhops'")

# --------------------------- Health -------------------------
@app.get("/health")
def health():
    return {"ok": True}

# -------- Local/mounted path flow (useful for local dev) ---
@app.post("/api/diagram")
def make_diagram(req: DiagramRequest, _=Depends(require_api_key)):
    return _generate(
        project_dir=Path(req.project_dir).resolve(),
        package_dir=req.package_dir,
        app_module=req.app_module,
        prefix=req.prefix,
        render=req.render,
        include_artifacts=req.include_artifacts,
        graph_mode=req.graph_mode,       # <-- pass through
        max_hops=req.max_hops,           # <-- pass through
    )

# ------------- Hosted flow: upload a .zip of the project ---------------
@app.post("/api/diagram-zip")
async def make_diagram_zip(
    file: UploadFile = File(..., description="Zip of the project directory"),
    package_dir: Optional[str] = Form(None),
    app_module: Optional[str] = Form(None),
    prefix: str = Form("app"),
    render: str = Form("mermaid"),
    include_artifacts: bool = Form(True),
    graph_mode: str = Form("api"),
    max_hops: int = Form(1),
    _=Depends(require_api_key),
):
    if render not in ("mermaid", "svg"):
        raise HTTPException(422, "render must be 'mermaid' or 'svg'")

    with tempfile.TemporaryDirectory() as tmp:
        proj_dir = Path(tmp) / "project"
        zip_bytes = await file.read()
        _safe_unzip_to(zip_bytes, proj_dir)
        return _generate(
            project_dir=proj_dir.resolve(),
            package_dir=package_dir,
            app_module=app_module,
            prefix=prefix,
            render=render,
            include_artifacts=include_artifacts,
            graph_mode=graph_mode,
            max_hops=max_hops,
        )
