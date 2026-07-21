# Starts korean-reader: rebuilds web/ if the source is newer than the last
# build, launches the FastAPI server (serves the API and the built frontend
# together on one port), and opens the browser.
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$webDir = Join-Path $root "web"
$outDir = Join-Path $webDir "out"

function Get-LatestWriteTime($path, [string[]]$excludePatterns) {
    if (-not (Test-Path $path)) { return $null }
    Get-ChildItem -Path $path -Recurse -File |
        Where-Object {
            $full = $_.FullName
            -not ($excludePatterns | Where-Object { $full -match $_ })
        } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty LastWriteTime
}

$sourceExcludes = @("\\node_modules\\", "\\\.next\\", "\\out\\")
$sourceTime = Get-LatestWriteTime $webDir $sourceExcludes
$outputTime = Get-LatestWriteTime $outDir @()

if ($null -eq $outputTime -or ($null -ne $sourceTime -and $sourceTime -gt $outputTime)) {
    Write-Host "web/ build is stale or missing — rebuilding..."
    Push-Location $webDir
    npm run build
    Pop-Location
} else {
    Write-Host "web/ build is up to date, skipping rebuild."
}

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "& '$py' -m uvicorn server.main:app --host 0.0.0.0 --port 8002" -WorkingDirectory $root

Start-Sleep -Seconds 3
Start-Process "http://localhost:8002"
