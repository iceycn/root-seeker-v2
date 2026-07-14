$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$env:ROOTSEEKER_STORAGE_BACKEND = "sqlite"
$env:ROOTSEEKER_SQLITE_DB_PATH = "data/rootseeker.db"
$env:ROOTSEEKER_ZOEKT_ENDPOINT = "http://127.0.0.1:6070"
$env:ROOTSEEKER_ZOEKT_INDEX_ENDPOINT = "http://127.0.0.1:6071"
$env:ROOTSEEKER_QDRANT_ENDPOINT = "http://127.0.0.1:6333"
$env:ROOTSEEKER_REPO_ENABLE_GITNEXUS = "true"
$env:ROOTSEEKER_GITNEXUS_ENDPOINT = "http://127.0.0.1:7474"

# Prefer project ./repos. If empty but Windows translated /data/repos clones exist
# (E:\data\repos), junction them so Zoekt/GitNexus hybrid mounts see the same trees.
$projectRepos = Join-Path (Get-Location) "repos"
$dataRepos = Join-Path ((Get-Location).Drive.Name + ":\") "data\repos"
if (-not (Test-Path $projectRepos)) {
    New-Item -ItemType Directory -Force -Path $projectRepos | Out-Null
}
$projectCount = @(Get-ChildItem $projectRepos -Directory -ErrorAction SilentlyContinue).Count
$dataCount = if (Test-Path $dataRepos) { @(Get-ChildItem $dataRepos -Directory -ErrorAction SilentlyContinue).Count } else { 0 }
$reposItem = Get-Item $projectRepos -Force
$isJunction = [bool]($reposItem.Attributes -band [IO.FileAttributes]::ReparsePoint)
if ($projectCount -eq 0 -and $dataCount -gt 0 -and -not $isJunction) {
    Write-Host "Linking empty ./repos -> $dataRepos (existing host clones from /data/repos)"
    Remove-Item $projectRepos -Force
    cmd /c "mklink /J `"$projectRepos`" `"$dataRepos`"" | Out-Host
}

$env:ROOTSEEKER_REPO_BASE_PATH = "repos"
$reposAbs = (Resolve-Path "repos").Path
$env:ROOTSEEKER_GITNEXUS_PATH_MAP = "${reposAbs}:/data/repos"
$env:ROOTSEEKER_ZOEKT_PATH_MAP = "${reposAbs}:/repos"
$env:ADMIN_HOST = "127.0.0.1"
$env:ADMIN_PORT = "8010"

# Hybrid: host uvicorn + docker indexers (full stack already wires gitnexus in compose)
try {
    if ($env:HTTP_PROXY -match "127\.0\.0\.1:10808" -or $env:HTTPS_PROXY -match "127\.0\.0\.1:10808") {
        Remove-Item Env:HTTP_PROXY, Env:HTTPS_PROXY, Env:http_proxy, Env:https_proxy -ErrorAction SilentlyContinue
    }
    docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up -d --build zoekt qdrant gitnexus | Out-Host
} catch {
    Write-Warning "docker compose up hybrid indexers failed: $_"
}

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
Write-Host "Repo base: $reposAbs"
Write-Host "Zoekt search: $env:ROOTSEEKER_ZOEKT_ENDPOINT"
Write-Host "Zoekt index:  $env:ROOTSEEKER_ZOEKT_INDEX_ENDPOINT"
Write-Host "Zoekt path map: $env:ROOTSEEKER_ZOEKT_PATH_MAP"
Write-Host "GitNexus endpoint: $env:ROOTSEEKER_GITNEXUS_ENDPOINT"
Write-Host "GitNexus path map: $env:ROOTSEEKER_GITNEXUS_PATH_MAP"
Write-Host "Full init deploy: docker compose up -d --build"
