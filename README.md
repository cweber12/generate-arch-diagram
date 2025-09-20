
# Architecture Diagram Service

Generate architecture diagrams for FastAPI projects using static analysis and route inspection. This service provides a REST API to generate Mermaid diagrams and SVGs from your Python codebase, visualizing endpoints and call graphs.

---

## Requirements

- Python 3.10+
- FastAPI
- Mermaid CLI (`mmdc`) for SVG rendering (install via `npm i -g @mermaid-js/mermaid-cli`)
- Node.js (for Mermaid CLI)
- Other dependencies listed in `requirements.txt`

## Setup

1. Clone the repository:

   ```powershell
   git clone https://github.com/cweber12/generate-arch-diagram.git
   cd generate-arch-diagram
   ```

2. Install Python dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Install Mermaid CLI (for SVG output):

   ```powershell
   npm install -g @mermaid-js/mermaid-cli
   ```

4. Generate an API key and its SHA256 hash:

  See the section below for details.

---

## Generating an API Key

To generate a secure API key and its SHA256 hash for server authentication, use the provided script:

```powershell
python scripts/gen_key.py
```

This will output something like:

```txt
API_KEY to give users: <your-random-api-key>
API_KEY_SHA256 for server env: <sha256-hash>
```

- Provide the `API_KEY` to users/clients for authentication.
- Set the `API_KEY_SHA256` value in your server's environment (e.g., in `.env` as `API_KEY_SHA256=<sha256-hash>`).

---

## Add Function to PowerShell Profile

Add a function to your PowerShell profile to automatically make all necessary CLI calls.

### Create PowerShell Profile

```powershell
if (-not (Test-Path -Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}
```

### Edit Profile in Notepad

```powershell
notepad $PROFILE
```

### Add Function

```powershell
function ArchDiagram {
  param(
    [string]$ApiBase    = "http://localhost:8911",
    [string]$ProjectDir = (Get-Location).Path,
    [string]$PackageDir = "app",
    [string]$Prefix     = "app",
    [ValidateSet("mermaid","svg")] [string]$Render = "mermaid",
    [ValidateSet("api","nhops","full")] [string]$GraphMode = "api",
    [int]$MaxHops = 1,
    [ValidateSet("TD","TB","LR","RL","BT")] [string]$Layout = "LR",
    [string]$AppModule
  )

  if (-not $env:DIAGRAM_API_KEY) { throw "Set `$env:DIAGRAM_API_KEY (plaintext key) first." }

  $payload = @{
    project_dir       = $ProjectDir
    package_dir       = $PackageDir
    prefix            = $Prefix
    render            = $Render
    include_artifacts = $true
    graph_mode        = $GraphMode
    max_hops          = $MaxHops
    layout_dir        = $Layout
  }
  if ($AppModule) { $payload.app_module = $AppModule }

  $json = $payload | ConvertTo-Json -Compress

  $params = @{
    Uri         = "$ApiBase/api/diagram"
    Method      = 'POST'
    Headers     = @{ 'X-API-Key' = $env:DIAGRAM_API_KEY }
    ContentType = 'application/json'
    Body        = $json
    ErrorAction = 'Stop'
  }

  try {
    $resp = Invoke-RestMethod @params

    # Optional: show SVG renderer error if server included one
    if ($resp.svg_error) {
      Write-Host "SVG render error (server):" -ForegroundColor Yellow
      ($resp.svg_error | Out-String) | Write-Host
    }

    if ($null -ne $resp.mermaid) {
      Set-Content -Path (Join-Path $ProjectDir "diagram.mmd") -Value $resp.mermaid -Encoding UTF8
      $mdText = @('```mermaid', ($resp.mermaid.TrimEnd()), '```') -join "`r`n"
      Set-Content -Path (Join-Path $ProjectDir "diagram.md") -Value $mdText -Encoding UTF8
      Write-Host "Wrote diagram.mmd, diagram.md" -ForegroundColor Green
    }

    if ($null -ne $resp.svg) {
      Set-Content -Path (Join-Path $ProjectDir "diagram.svg") -Value $resp.svg -Encoding UTF8
      Write-Host "Wrote diagram.svg" -ForegroundColor Green
    } elseif ($Render -eq "svg") {
      Write-Host "Server did not return SVG (is Mermaid CLI available on server?). Saved .mmd/.md." -ForegroundColor Yellow
    }

    if ($resp.artifacts.'routes.json') {
      Set-Content -Path (Join-Path $ProjectDir "routes.json") -Value $resp.artifacts.'routes.json' -Encoding UTF8
      Write-Host "Wrote routes.json" -ForegroundColor Green
    }
    if ($resp.artifacts.'callgraph.json') {
      Set-Content -Path (Join-Path $ProjectDir "callgraph.json") -Value $resp.artifacts.'callgraph.json' -Encoding UTF8
      Write-Host "Wrote callgraph.json" -ForegroundColor Green
    }
  }
  catch {
    Write-Host "Request failed:" -ForegroundColor Red
    # Print server error body (includes tool STDOUT/STDERR from your FastAPI _run())
    try {
      $respStream = $_.Exception.Response.GetResponseStream()
      if ($respStream) {
        $sr   = New-Object System.IO.StreamReader($respStream)
        $body = $sr.ReadToEnd()
        Write-Host "`n---- SERVER ERROR BODY ----`n$body" -ForegroundColor Yellow
        # (Optional) Save to a local file for inspection
        $errPath = Join-Path $ProjectDir "diagram_error.txt"
        $body | Set-Content -Path $errPath -Encoding UTF8
        Write-Host "Saved server error to $errPath" -ForegroundColor Yellow
      } else {
        $_ | Out-String | Write-Host
      }
    } catch {
      $_ | Out-String | Write-Host
    }
    throw
  }
}
```

### Reload Profile

```powershell
. $PROFILE
```

---

### Calling the Endpoint from the Project Root

#### Call graph only, scan the 'app' folder, save all files

```powershell
New-ArchDiagram -ProjectDir "C:\Projects\RouteMap\backend_match" -PackageDir app -Prefix app -Render mermaid
```

#### Include FastAPI routes as well (adjust to your real module path)

```powershell
New-ArchDiagram -ProjectDir "C:\Projects\RouteMap\backend_match" -PackageDir app -Prefix app `
  -AppModule "app.main:app" -Render mermaid
```

#### Ask the server for SVG too (requires Mermaid CLI configured on server)

```powershell
New-ArchDiagram -ProjectDir "C:\Projects\RouteMap\backend_match" -PackageDir app -Prefix app -Render svg
```