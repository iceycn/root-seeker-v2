$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$env:ROOTSEEKER_STORAGE_BACKEND = "sqlite"
$env:ROOTSEEKER_SQLITE_DB_PATH = "data/rootseeker.db"
$env:ROOTSEEKER_ZOEKT_ENDPOINT = "http://127.0.0.1:6070"
$env:ROOTSEEKER_QDRANT_ENDPOINT = "http://127.0.0.1:6333"
$env:ROOTSEEKER_REPO_BASE_PATH = "repos"
$env:ADMIN_HOST = "127.0.0.1"
$env:ADMIN_PORT = "8010"

$python = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Start-Process -FilePath $python -ArgumentList @(
    "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000"
) -WorkingDirectory (Get-Location) -WindowStyle Hidden

Start-Process -FilePath $python -ArgumentList @(
    "-m", "uvicorn", "apps.admin.main:app", "--host", "127.0.0.1", "--port", "8010"
) -WorkingDirectory (Get-Location) -WindowStyle Hidden

Write-Host "Started API (:8000) and Admin (:8010)"
