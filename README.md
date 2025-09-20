# ARCH DIAGRAM GENERATION

## ADD FUNCTION TO POWERSHELL PROFILE

### CREATE POWERSHELL PROFILE

```bash
if (-not (Test-Path -Path $PROFILE)) {                        
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}
```

### EDIT PROFILE IN NOTEPAD

```bash
notepad $PROFILE 
```

### ADD FUNCTION

```bash
function ArchDiagram {
  param(
    [string]$ApiBase    = "http://localhost:8911",
    [string]$ProjectDir = (Get-Location).Path,
    [string]$PackageDir = "app",
    [string]$Prefix     = "app",
    [ValidateSet("mermaid","svg")] [string]$Render = "mermaid",
    [ValidateSet("api","nhops","full")] [string]$GraphMode = "api",
    [int]$MaxHops = 1,
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
  } catch {
    Write-Host "Request failed:" -ForegroundColor Red
    $_ | Out-String | Write-Host
  }
}
```

### RELOAD PROFILE

```bash
. $PROFILE 
```

### CALLING THE ENDPOINT FROM THE PROJECT ROOT

#### Call graph only, scan the 'app' folder, save all files

```bash
New-ArchDiagram -ProjectDir "C:\Projects\RouteMap\backend_match" -PackageDir app -Prefix app -Render mermaid
```

#### Include FastAPI routes as well (adjust to your real module path)

```bash
New-ArchDiagram -ProjectDir "C:\Projects\RouteMap\backend_match" -PackageDir app -Prefix app `
  -AppModule "app.main:app" -Render mermaid
```

#### Ask the server for SVG too (requires Mermaid CLI configured on server)

```bash
New-ArchDiagram -ProjectDir "C:\Projects\RouteMap\backend_match" -PackageDir app -Prefix app -Render svg