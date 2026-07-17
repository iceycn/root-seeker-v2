# Build / tag / push RootSeeker V2 images to Docker Hub.
# Prerequisites:
#   docker login
#   $env:DOCKERHUB_USER = "your-hub-username"
#
# Usage:
#   .\scripts\push-dockerhub.ps1
#   .\scripts\push-dockerhub.ps1 -User myname -Tag v0.1.0
#   .\scripts\push-dockerhub.ps1 -SkipBuild   # only retag + push existing local images

param(
    [string]$User = $(if ($env:DOCKERHUB_USER) { $env:DOCKERHUB_USER } else { "wuhun0301" }),
    [string]$Tag = $(if ($env:IMAGE_TAG) { $env:IMAGE_TAG } else { "latest" }),
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $User) {
    throw "请设置 Docker Hub 用户名：-User <name> 或 `$env:DOCKERHUB_USER"
}

Write-Host "[info] DOCKERHUB_USER=$User  TAG=$Tag"

# Ensure Zoekt binaries exist for zoekt image build
$zoektIndex = Join-Path $Root "docker\bin\zoekt-index"
$zoektWeb = Join-Path $Root "docker\bin\zoekt-webserver"
if (-not (Test-Path $zoektIndex) -or -not (Test-Path $zoektWeb)) {
    Write-Host "[info] downloading Zoekt binaries..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "docker\prepare-zoekt.ps1")
}

if (-not $SkipBuild) {
    Write-Host "[info] building images (compose)..."
    docker compose build api zoekt gitnexus
    if ($LASTEXITCODE -ne 0) { throw "docker compose build failed" }
}

$appLocal = "root-seeker-v2-api:latest"
$zoektLocal = "root-seeker-v2-zoekt:latest"
$gitnexusLocal = "root-seeker-v2-gitnexus:latest"

$appRemote = "${User}/rootseeker-v2:${Tag}"
$zoektRemote = "${User}/rootseeker-v2-zoekt:${Tag}"
$gitnexusRemote = "${User}/rootseeker-v2-gitnexus:${Tag}"

$pairs = @(
    @{ Local = $appLocal; Remote = $appRemote },
    @{ Local = $zoektLocal; Remote = $zoektRemote },
    @{ Local = $gitnexusLocal; Remote = $gitnexusRemote }
)

foreach ($p in $pairs) {
    Write-Host "[tag] $($p.Local) -> $($p.Remote)"
    docker tag $p.Local $p.Remote
    if ($LASTEXITCODE -ne 0) { throw "docker tag failed: $($p.Remote)" }
}

foreach ($p in $pairs) {
    Write-Host "[push] $($p.Remote)"
    docker push $p.Remote
    if ($LASTEXITCODE -ne 0) { throw "docker push failed: $($p.Remote). 请先执行 docker login" }
}

if ($Tag -ne "latest") {
    foreach ($name in @("rootseeker-v2", "rootseeker-v2-zoekt", "rootseeker-v2-gitnexus")) {
        $src = "${User}/${name}:${Tag}"
        $dst = "${User}/${name}:latest"
        Write-Host "[tag] $src -> $dst"
        docker tag $src $dst
        Write-Host "[push] $dst"
        docker push $dst
        if ($LASTEXITCODE -ne 0) { throw "docker push failed: $dst" }
    }
}

Write-Host ""
Write-Host "[ok] pushed:"
Write-Host "  docker.io/$appRemote"
Write-Host "  docker.io/$zoektRemote"
Write-Host "  docker.io/$gitnexusRemote"
Write-Host ""
Write-Host "pull & run:"
Write-Host "  `$env:DOCKERHUB_USER='$User'"
Write-Host "  docker compose -f docker-compose.yml -f docker-compose.pull.yml up -d"
