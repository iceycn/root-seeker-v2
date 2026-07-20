@echo off
REM RootSeeker V2 - Quick Start Script (Windows)
REM Usage:
REM   start.bat           - Docker Compose up (default)
REM   start.bat k8s       - Kubernetes deploy
REM   start.bat stop      - Stop all Docker services
REM   start.bat stop k8s  - Remove K8s resources
REM   start.bat status    - Check service status
REM   start.bat build     - Build images only

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "COMMAND=%~1"
set "MODE=%~2"

if "%COMMAND%"=="" set "COMMAND=up"
if "%MODE%"=="" set "MODE=docker"

if "%COMMAND%"=="up" goto :docker_up
if "%COMMAND%"=="start" goto :docker_up
if "%COMMAND%"=="k8s" goto :k8s_deploy
if "%COMMAND%"=="down" goto :docker_down
if "%COMMAND%"=="stop" (
    if "%MODE%"=="k8s" goto :k8s_down
    goto :docker_down
)
if "%COMMAND%"=="build" goto :docker_build
if "%COMMAND%"=="status" (
    if "%MODE%"=="k8s" goto :k8s_status
    goto :docker_status
)
if "%COMMAND%"=="ps" (
    if "%MODE%"=="k8s" goto :k8s_status
    goto :docker_status
)
goto :usage

:ensure_zoekt_bins
if exist "docker\bin\zoekt-index" if exist "docker\bin\zoekt-webserver" goto :eof
echo [INFO] Zoekt binaries missing; downloading via docker\prepare-zoekt.ps1 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%docker\prepare-zoekt.ps1"
goto :eof

:docker_build
call :ensure_zoekt_bins
echo [INFO] Building RootSeeker V2 Docker images...
docker compose build
echo [OK] Images built successfully.
goto :eof

:docker_up
if not exist .env (
    echo [INFO] No .env file found, creating from template...
    copy .env.docker .env
    echo [WARN] Review .env and configure LLM keys if needed.
)
call :ensure_zoekt_bins
echo [INFO] Syncing compose storage profiles...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$backend='mysql'; if (Test-Path '.env') { $m = Select-String -Path '.env' -Pattern '^ROOTSEEKER_STORAGE_BACKEND=(.*)$' | Select-Object -Last 1; if ($m) { $backend = $m.Matches[0].Groups[1].Value.Trim().Trim('\"').Trim('''') } }; if ($backend -eq 'sqlite' -or $backend -eq 'memory') { $env:COMPOSE_PROFILES=''; Write-Host '[INFO] storage=' $backend '-> mysql profile OFF' } else { $env:COMPOSE_PROFILES='mysql'; Write-Host '[INFO] storage=' $backend '-> mysql profile ON' }; docker compose up -d --build"
echo.
echo [OK] RootSeeker V2 is starting!
echo.
echo   Services:
echo     API:        http://localhost:8000
echo     Admin:      http://localhost:8010
echo     Zoekt:      http://localhost:6070
echo     Qdrant:     http://localhost:6333
echo     GitNexus:   http://localhost:7474
echo     MySQL:      internal network only when STORAGE_BACKEND=mysql
echo.
echo   Health check:
echo     curl http://localhost:8000/healthz
echo     curl http://localhost:8010/healthz
echo     curl http://localhost:7474/healthz
echo.
echo   View logs:
echo     docker compose logs -f api
echo     docker compose logs -f admin
echo.
echo   Stop:
echo     start.bat stop
echo.
goto :eof

:docker_down
echo [INFO] Stopping RootSeeker V2 services...
docker compose down
echo [OK] All services stopped.
goto :eof

:docker_status
echo [INFO] RootSeeker V2 Service Status:
echo.
docker compose ps
echo.
for %%s in (api admin) do (
    curl -sf http://localhost:8000/healthz >nul 2>&1 && echo [OK] api is healthy || echo [WARN] api is not responding
)
goto :eof

:k8s_deploy
echo [INFO] Building Docker images for Kubernetes...
docker build -t rootseeker:latest .
docker build -t rootseeker-zoekt:latest -f docker\Dockerfile.zoekt docker\
docker build -t rootseeker-gitnexus:latest -f docker\Dockerfile.gitnexus .
echo.
echo [INFO] Deploying RootSeeker V2 to Kubernetes...
kubectl apply -k k8s/
echo.
echo [OK] RootSeeker V2 deployed!
echo.
echo   Wait for pods:
echo     kubectl get pods -n rootseeker -w
echo.
echo   Port-forward for local access:
echo     kubectl port-forward -n rootseeker svc/api 8000:8000
echo     kubectl port-forward -n rootseeker svc/admin 8010:8010
echo.
goto :eof

:k8s_down
echo [INFO] Removing RootSeeker V2 from Kubernetes...
kubectl delete -k k8s/ --ignore-not-found=true
echo [OK] All resources removed.
goto :eof

:k8s_status
echo [INFO] RootSeeker V2 Kubernetes Status:
echo.
kubectl get all -n rootseeker
echo.
kubectl get pvc -n rootseeker
goto :eof

:usage
echo Usage: start.bat [up^|down^|build^|status^|k8s] [docker^|k8s]
echo.
echo Commands:
echo   up / start    Start all services (default)
echo   down / stop   Stop all services
echo   k8s           Deploy to Kubernetes
echo   build         Build Docker images only
echo   status / ps   Show service status
echo.
echo Examples:
echo   start.bat              Docker Compose up
echo   start.bat k8s          Kubernetes deploy
echo   start.bat stop         Docker Compose down
echo   start.bat stop k8s     Kubernetes remove
echo   start.bat status       Check Docker services
goto :eof
