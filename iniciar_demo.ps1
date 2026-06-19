# =====================================================================
#  Hampton by Hilton Bariloche — Arranque de la demo
#  Levanta el BACKEND (FastAPI :8010) y la LANDING (Vite :5174).
#  Uso:  click derecho > "Ejecutar con PowerShell"   o   .\iniciar_demo.ps1
# =====================================================================

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host ""
Write-Host "  Hampton by Hilton Bariloche - Demo" -ForegroundColor Cyan
Write-Host "  ===================================" -ForegroundColor Cyan
Write-Host ""

# --- Backend ---------------------------------------------------------
$backend = Join-Path $root "backend"
$venvPy  = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { $venvPy = "python" }  # fallback al python global

Write-Host "  [1/2] Iniciando backend (FastAPI) en http://localhost:8010 ..." -ForegroundColor Yellow
Start-Process -FilePath $venvPy `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8010" `
  -WorkingDirectory $backend `
  -WindowStyle Minimized

# --- Landing ---------------------------------------------------------
$landing = Join-Path $root "landing"
Write-Host "  [2/2] Iniciando landing (Vite) en http://localhost:5174 ..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" `
  -ArgumentList "/c","npm run dev" `
  -WorkingDirectory $landing `
  -WindowStyle Minimized

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "  Demo lista:" -ForegroundColor Green
Write-Host "    - Sitio publico + agente:  http://localhost:5174" -ForegroundColor White
Write-Host "    - Backoffice:              http://localhost:5174/#admin" -ForegroundColor White
Write-Host "    - API backend:             http://localhost:8010/docs" -ForegroundColor White
Write-Host ""
Write-Host "  (Las ventanas del backend y la landing quedan minimizadas)" -ForegroundColor DarkGray
Write-Host ""

# Abrir el navegador en la landing
Start-Process "http://localhost:5174"
