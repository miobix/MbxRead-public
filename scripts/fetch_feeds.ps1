# Epic 17: hits the running MbxRead server's fetch endpoint on a schedule.
# Register this as a Windows Task Scheduler action (see README.md) on a daily
# trigger. Assumes the server is already up (Tailscale-hosted, always running) —
# this script does not start it, just calls the same endpoint the Queue page's
# "Fetch new candidates" button does.

$ErrorActionPreference = "Stop"
$logPath = Join-Path $PSScriptRoot "fetch_feeds.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    $response = Invoke-RestMethod -Uri "http://localhost:8002/api/feeds/fetch" -Method Post
    $summary = $response | ConvertTo-Json -Compress -Depth 5
    Add-Content -Path $logPath -Value "$timestamp OK $summary" -Encoding utf8
}
catch {
    Add-Content -Path $logPath -Value "$timestamp ERROR $($_.Exception.Message)" -Encoding utf8
    exit 1
}
