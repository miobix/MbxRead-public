# Starts Lute (reader, :5001) and the translate service (:8001) in two windows.
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "& '$py' -m lute.main --port 5001" -WorkingDirectory $root
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "& '$py' -m uvicorn translate_svc.main:app --host 0.0.0.0 --port 8001" -WorkingDirectory $root

Start-Sleep -Seconds 3
Start-Process "http://localhost:5001"
