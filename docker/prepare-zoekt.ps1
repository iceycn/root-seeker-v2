# Download Zoekt binaries on the host (uses local proxy). Run before: docker compose build zoekt
$ErrorActionPreference = "Stop"
$BinDir = Join-Path $PSScriptRoot "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$proxy = $env:HTTPS_PROXY
if (-not $proxy) { $proxy = $env:HTTP_PROXY }
if (-not $proxy) { $proxy = "http://127.0.0.1:10808" }

$env:HTTP_PROXY = $proxy
$env:HTTPS_PROXY = $proxy

$version = "v0.0.0-2024-11-13"
$base = "https://github.com/sourcegraph/zoekt/releases/download/$version"
$arch = "linux_amd64"

foreach ($name in @("zoekt-webserver", "zoekt-index")) {
    $out = Join-Path $BinDir $name
    if (Test-Path $out) {
        Write-Host "[skip] $name already exists"
        continue
    }
    $url = "$base/${name}_$arch.tar.gz"
    $tgz = Join-Path $env:TEMP "${name}_$arch.tar.gz"
    Write-Host "[download] $url"
    curl.exe -fsSL -x $proxy -o $tgz $url
    tar -xzf $tgz -C $BinDir
    Remove-Item $tgz -Force
    Write-Host "[ok] $name"
}

Write-Host "Zoekt binaries ready in $BinDir"
