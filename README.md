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
function New-ArchDiagram {
  param(
    [ValidateSet("mermaid","svg")] [string]$Render = "mermaid",
    [string]$Prefix = "app",
    [string]$AppModule,
    [string]$ApiBase = "http://localhost:8911"  
  )

  if (-not $env:DIAGRAM_API_KEY) {
    throw "Set `$env:DIAGRAM_API_KEY (plaintext key) first:  `$env:DIAGRAM_API_KEY = 'BbsGmr7W6UTslHPcf0ojniLzcxjP0nMSG5nS7Jx5jbY'"
  }

  $payload = @{
    project_dir = (Get-Location).Path
    prefix      = $Prefix
    render      = $Render
  }
  if ($AppModule) { $payload.app_module = $AppModule }

  $json = $payload | ConvertTo-Json

  try {
    $resp = Invoke-RestMethod -Uri "$ApiBase/api/diagram" -Method POST `
            -Headers @{ "X-API-Key"=$env:DIAGRAM_API_KEY; "Content-Type"="application/json" } `
            -Body $json

    if ($resp.svg) {
      Set-Content -Path ".\diagram.svg" -Value $resp.svg -Encoding UTF8
      Write-Host "Wrote diagram.svg" -ForegroundColor Green
    } elseif ($resp.mermaid) {
      Set-Content -Path ".\diagram.mmd" -Value $resp.mermaid -Encoding UTF8
      Write-Host "Wrote diagram.mmd" -ForegroundColor Green
    } else {
      Write-Host "No diagram returned." -ForegroundColor Yellow
    }
  }
  catch {
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