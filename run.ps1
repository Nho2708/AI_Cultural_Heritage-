# Chạy dịch vụ AI ở http://localhost:8000 (hoặc cổng khác: .\run.ps1 -Port 8001).
# Khóa đọc từ .env trong thư mục này rồi %APPDATA%\DSVHVN\ai-service.env; script không đọc và không in khóa.
param(
    [int]$Port = 8000,
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Chưa có .venv. Chạy: py -3.14 -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
}

$env:PYTHONUTF8 = "1"
& $python -m uvicorn app.asgi:app --host $BindHost --port $Port
