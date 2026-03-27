# restart.ps1 — Kill and relaunch Crucible backend + frontend

$ROOT = $PSScriptRoot
$WEB  = Join-Path $ROOT "web"

Write-Host "Stopping processes on ports 8000 and 5173..." -ForegroundColor Yellow

foreach ($port in 8000, 5173) {
    $pids = netstat -ano | Select-String ":$port\s" | ForEach-Object {
        ($_ -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$' -and $p -ne '0') {
            try {
                taskkill /PID $p /F 2>$null | Out-Null
                Write-Host "  Killed PID $p (port $port)" -ForegroundColor Gray
            } catch {}
        }
    }
}

Start-Sleep -Milliseconds 500

Write-Host "Starting backend (port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$ROOT'; python -m uvicorn api.main:app --reload --port 8000"

Start-Sleep -Milliseconds 1000

Write-Host "Starting frontend (port 5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$WEB'; npm run dev"

Write-Host "Done. Backend: http://localhost:8000 | Frontend: http://localhost:5173" -ForegroundColor Green
