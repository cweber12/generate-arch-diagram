from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
import os, hashlib, secrets, tempfile, pathlib, shutil, subprocess

from dotenv import load_dotenv
load_dotenv() 

app = FastAPI(title="Architecture Diagram Service", version="0.1.0")

API_KEY_HEADER = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)
API_KEY_SHA256 = os.getenv("API_KEY_SHA256")

if not API_KEY_SHA256:
    raise RuntimeError("Missing API_KEY_SHA256 env var")

SERVICE_ROOT = pathlib.Path(__file__).resolve().parents[1]  # repo root

def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    if not api_key:
        raise HTTPException(401, "Missing API key", headers={"WWW-Authenticate": "ApiKey"})
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    if not secrets.compare_digest(digest, API_KEY_SHA256):
        raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "ApiKey"})

def _run(cmd: list[str], cwd: pathlib.Path, env: dict | None = None) -> str:
    try:
        res = subprocess.run(cmd, cwd=str(cwd), env=env, check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.stdout
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Command failed: {' '.join(cmd)}\n{e.stderr}")

class DiagramRequest(BaseModel):
    project_dir: str = Field(..., description="Absolute path to the repo to analyze")
    app_module: Optional[str] = Field(None, description="FastAPI app spec, e.g. 'app.main:app'")
    prefix: str = Field("app", description="Limit callgraph to a package prefix")
    render: str = Field("mermaid", pattern="^(mermaid|svg)$")

@app.post("/api/diagram")
def make_diagram(req: DiagramRequest, _=Depends(require_api_key)):
    project_dir = pathlib.Path(req.project_dir).resolve()
    if not project_dir.exists():
        raise HTTPException(400, f"project_dir does not exist: {project_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        routes_json = tmp_path / "routes.json"
        callgraph_json = tmp_path / "callgraph.json"

        # 1) Export FastAPI routes (optional)
        if req.app_module:
            env = os.environ.copy()
            env["APP_MODULE"] = req.app_module
            # Ensure the target project is importable:
            env["PYTHONPATH"] = f"{project_dir}{os.pathsep}{env.get('PYTHONPATH','')}"
            _run(
                ["python", "-m", "tools.export_routes", "--out", str(routes_json)],
                cwd=project_dir,
                env=env
            )
        else:
            routes_json.write_text("[]", encoding="utf-8")

        # 2) Build callgraph
        _run(
            ["python", "-m", "tools.callgraph_ast", str(project_dir), "--out", str(callgraph_json), "--prefix", req.prefix],
            cwd=project_dir
        )

        # 3) Mermaid text (tools/mermaid.py looks for JSONs in its own ROOT)
        service_routes = SERVICE_ROOT / "routes.json"
        service_callgraph = SERVICE_ROOT / "callgraph.json"
        service_routes.write_text(routes_json.read_text(encoding="utf-8"), encoding="utf-8")
        service_callgraph.write_text(callgraph_json.read_text(encoding="utf-8"), encoding="utf-8")

        mermaid_txt = _run(["python", "-m", "tools.mermaid"], cwd=SERVICE_ROOT)

        if req.render == "mermaid":
            return {"mermaid": mermaid_txt}

        # 4) Optional: SVG via Mermaid CLI (requires @mermaid-js/mermaid-cli installed)
        mmd = tmp_path / "diagram.mmd"
        svg = tmp_path / "diagram.svg"
        mmd.write_text(mermaid_txt, encoding="utf-8")
        _run(["mmdc", "-i", str(mmd), "-o", str(svg), "-b", "transparent"], cwd=SERVICE_ROOT)
        return {"svg": svg.read_text(encoding="utf-8"), "format": "svg"}
