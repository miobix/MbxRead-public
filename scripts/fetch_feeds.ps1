# Daily Task Scheduler action: calls the running server's fetch endpoint, the same one
# the Queue's "Fetch new candidates" button uses. Does not start the server.

$ErrorActionPreference = "Stop"
$logPath = Join-Path $PSScriptRoot "fetch_feeds.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8002/api/feeds/fetch" -Method Post -UseBasicParsing
    # PowerShell 5.1 decodes a charset-less application/json as Latin-1; read the bytes as UTF-8.
    $summary = [Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
    Add-Content -Path $logPath -Value "$timestamp OK $summary" -Encoding utf8
}
catch {
    Add-Content -Path $logPath -Value "$timestamp ERROR $($_.Exception.Message)" -Encoding utf8
    exit 1
}
