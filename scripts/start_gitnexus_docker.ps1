$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

# Hybrid helper only: host uvicorn + docker indexers (zoekt/qdrant/gitnexus).
# Full init deploy already includes gitnexus via: docker compose up -d --build
#
# Optional proxy (China): set HTTP_PROXY/HTTPS_PROXY before running, e.g.
#   $env:HTTP_PROXY = "http://127.0.0.1:10808"

New-Item -ItemType Directory -Force -Path "repos" | Out-Null

Write-Host "Starting hybrid indexers (zoekt/qdrant/gitnexus) with ./repos mount ..."
if ($env:HTTP_PROXY -match "127\.0\.0\.1:10808" -or $env:HTTPS_PROXY -match "127\.0\.0\.1:10808") {
    Write-Warning "Clearing dead local proxy 10808 for this build"
    Remove-Item Env:HTTP_PROXY, Env:HTTPS_PROXY, Env:http_proxy, Env:https_proxy -ErrorAction SilentlyContinue
}
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml build --build-arg HTTP_PROXY= --build-arg HTTPS_PROXY= --build-arg http_proxy= --build-arg https_proxy= gitnexus
if ($LASTEXITCODE -ne 0) {
    Write-Host "Hint: ensure node:22-slim exists locally (docker pull docker.1ms.run/node:22-slim && docker tag docker.1ms.run/node:22-slim node:22-slim)"
    throw "docker compose build gitnexus failed"
}
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up -d zoekt qdrant gitnexus
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up hybrid indexers failed"
}

$reposAbs = (Resolve-Path "repos").Path
Write-Host ""
Write-Host "Hybrid indexers ready. For local API/Admin set:"
Write-Host "  `$env:ROOTSEEKER_GITNEXUS_ENDPOINT = 'http://127.0.0.1:7474'"
Write-Host "  `$env:ROOTSEEKER_GITNEXUS_PATH_MAP = '$reposAbs:/data/repos'"
Write-Host "  `$env:ROOTSEEKER_REPO_ENABLE_GITNEXUS = 'true'"
Write-Host "  `$env:ROOTSEEKER_ZOEKT_ENDPOINT = 'http://127.0.0.1:6070'"
Write-Host "  `$env:ROOTSEEKER_ZOEKT_INDEX_ENDPOINT = 'http://127.0.0.1:6071'"
Write-Host "  `$env:ROOTSEEKER_ZOEKT_PATH_MAP = '$reposAbs:/repos'"
Write-Host ""
Write-Host "Full init deploy (all services including gitnexus): docker compose up -d --build"
