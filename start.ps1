# Start VeriDuka without Docker. Requires Python 3.11+ and Node.js 20+.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example. Add API keys there when you have them."
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not on PATH. Install Python 3.11 or newer, then run this script again."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "Node.js is not on PATH. Install Node.js 20 or newer, then run this script again."
}

$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  python -m venv (Join-Path $Root "backend\.venv")
}
& $Python -m pip install -r (Join-Path $Root "backend\requirements.txt")

if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
  Push-Location (Join-Path $Root "frontend")
  npm install
  Pop-Location
}

Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory (Join-Path $Root "backend")
Start-Process -FilePath "cmd.exe" -ArgumentList "/c","npm run dev -- --host 127.0.0.1 --port 5173" -WorkingDirectory (Join-Path $Root "frontend")
Start-Sleep -Seconds 2
Start-Process "http://localhost:5173"
Write-Host "VeriDuka is starting."
Write-Host "Dashboard: http://localhost:5173"
Write-Host "API docs:  http://127.0.0.1:8000/docs"
