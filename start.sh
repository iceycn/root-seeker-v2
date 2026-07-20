#!/usr/bin/env bash
# RootSeeker V2 - Quick Start Script
# Usage:
#   ./start.sh           # Docker Compose build+up (default)
#   ./start.sh --pull    # 使用 Docker Hub 预构建镜像（需 DOCKERHUB_USER）
#   ./start.sh k8s       # Kubernetes (kubectl)
#   ./start.sh stop      # Stop all services
#   ./start.sh status    # Check service status
#   ./start.sh build     # Build images only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

USE_PULL=0
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --pull) USE_PULL=1 ;;
        *) ARGS+=("$arg") ;;
    esac
done
set -- "${ARGS[@]:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ==============================
# Docker Compose Functions
# ==============================

ensure_zoekt_bins() {
    if [ ! -x "$SCRIPT_DIR/docker/bin/zoekt-index" ] || [ ! -x "$SCRIPT_DIR/docker/bin/zoekt-webserver" ]; then
        info "Zoekt binaries missing; downloading via docker/prepare-zoekt.sh ..."
        bash "$SCRIPT_DIR/docker/prepare-zoekt.sh"
    fi
}

docker_build() {
    ensure_zoekt_bins
    info "Building RootSeeker V2 Docker images..."
    docker compose build
    ok "Images built successfully."
}

docker_up() {
    # Ensure .env exists
    if [ ! -f .env ]; then
        info "No .env file found, creating from template..."
        cp .env.docker .env
        warn "Review .env and configure LLM keys if needed."
    fi

    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/scripts/sync-compose-storage.sh"
    sync_storage_compose_profiles

    if [ "$USE_PULL" = "1" ]; then
        if [ -z "${DOCKERHUB_USER:-}" ]; then
            error "使用 --pull 时请设置 DOCKERHUB_USER（Docker Hub 用户名）"
            exit 1
        fi
        info "Pulling images from Docker Hub (user=${DOCKERHUB_USER})..."
        docker compose -f docker-compose.yml -f docker-compose.pull.yml pull
        info "Starting RootSeeker V2 services (prebuilt images)..."
        docker compose -f docker-compose.yml -f docker-compose.pull.yml up -d
    else
        ensure_zoekt_bins
        info "Starting RootSeeker V2 services..."
        docker compose up -d --build
    fi

    echo ""
    ok "RootSeeker V2 is starting!"
    echo ""
    echo "  Services:"
    echo "    API:        http://localhost:${API_PORT:-8000}"
    echo "    Admin:      http://localhost:${ADMIN_PORT:-8010}"
    echo "    Zoekt:      http://localhost:${ZOEKT_PORT:-6070}"
    echo "    Qdrant:     http://localhost:${QDRANT_PORT:-6333}"
    echo "    GitNexus:   http://localhost:${GITNEXUS_PORT:-7474}"
    if [ "${COMPOSE_PROFILES:-}" = "mysql" ]; then
        echo "    MySQL:      (internal only — compose network, no host port)"
    fi
    echo ""
    echo "  Health check:"
    echo "    curl http://localhost:${API_PORT:-8000}/healthz"
    echo "    curl http://localhost:${ADMIN_PORT:-8010}/healthz"
    echo "    curl http://localhost:${GITNEXUS_PORT:-7474}/healthz"
    echo ""
    echo "  View logs:"
    echo "    docker compose logs -f api"
    echo "    docker compose logs -f admin"
    echo ""
    echo "  Stop:"
    echo "    ./start.sh stop"
    echo ""
}

docker_down() {
    info "Stopping RootSeeker V2 services..."
    docker compose down
    ok "All services stopped."
}

docker_status() {
    info "RootSeeker V2 Service Status:"
    echo ""
    docker compose ps
    echo ""
    # Quick health check
    for svc in api admin; do
        port=$(docker compose port "$svc" 2>/dev/null | cut -d: -f2 || true)
        if [ -n "$port" ]; then
            if curl -sf "http://localhost:$port/healthz" > /dev/null 2>&1; then
                ok "$svc is healthy (port $port)"
            else
                warn "$svc is not responding on port $port"
            fi
        fi
    done
}

# ==============================
# Kubernetes Functions
# ==============================

k8s_build() {
    info "Building and loading Docker images into Kubernetes..."

    # Build the main application image
    docker build -t rootseeker:latest .

    # Build the Zoekt image
    docker build -t rootseeker-zoekt:latest -f docker/Dockerfile.zoekt docker/

    # Build the GitNexus knowledge-graph sidecar
    docker build -t rootseeker-gitnexus:latest -f docker/Dockerfile.gitnexus .

    # Load into cluster (minikube/k3s)
    if command -v minikube > /dev/null 2>&1; then
        info "Loading images into minikube..."
        minikube image load rootseeker:latest
        minikube image load rootseeker-zoekt:latest
        minikube image load rootseeker-gitnexus:latest
    elif command -v k3s > /dev/null 2>&1; then
        info "Importing images into k3s..."
        k3s ctr images import <(docker save rootseeker:latest) 2>/dev/null || \
            docker save rootseeker:latest | k3s ctr images import - 2>/dev/null || true
        k3s ctr images import <(docker save rootseeker-zoekt:latest) 2>/dev/null || \
            docker save rootseeker-zoekt:latest | k3s ctr images import - 2>/dev/null || true
        k3s ctr images import <(docker save rootseeker-gitnexus:latest) 2>/dev/null || \
            docker save rootseeker-gitnexus:latest | k3s ctr images import - 2>/dev/null || true
    else
        warn "No minikube/k3s detected. Ensure your K8s cluster can pull these images."
    fi
    ok "Images built."
}

k8s_up() {
    info "Deploying RootSeeker V2 to Kubernetes..."
    kubectl apply -k k8s/

    echo ""
    ok "RootSeeker V2 deployed!"
    echo ""
    echo "  Wait for pods to be ready:"
    echo "    kubectl get pods -n rootseeker -w"
    echo ""
    echo "  Port-forward for local access:"
    echo "    kubectl port-forward -n rootseeker svc/api 8000:8000"
    echo "    kubectl port-forward -n rootseeker svc/admin 8010:8010"
    echo ""
    echo "  Or use Ingress (if configured):"
    echo "    http://rootseeker.local"
    echo ""
}

k8s_down() {
    info "Removing RootSeeker V2 from Kubernetes..."
    kubectl delete -k k8s/ --ignore-not-found=true
    ok "All resources removed."
}

k8s_status() {
    info "RootSeeker V2 Kubernetes Status:"
    echo ""
    kubectl get all -n rootseeker
    echo ""
    kubectl get pvc -n rootseeker
}

# ==============================
# Main
# ==============================

COMMAND="${1:-up}"
MODE="${2:-docker}"

case "$COMMAND" in
    up|start)
        if [ "$MODE" = "k8s" ]; then
            k8s_build
            k8s_up
        else
            docker_up
        fi
        ;;
    down|stop)
        if [ "$MODE" = "k8s" ]; then
            k8s_down
        else
            docker_down
        fi
        ;;
    build)
        if [ "$MODE" = "k8s" ]; then
            k8s_build
        else
            docker_build
        fi
        ;;
    status|ps)
        if [ "$MODE" = "k8s" ]; then
            k8s_status
        else
            docker_status
        fi
        ;;
    k8s)
        k8s_build
        k8s_up
        ;;
    *)
        echo "Usage: $0 [up|down|build|status] [docker|k8s]"
        echo ""
        echo "Commands:"
        echo "  up / start    Start all services (default)"
        echo "  down / stop   Stop all services"
        echo "  build         Build Docker images only"
        echo "  status / ps   Show service status"
        echo ""
        echo "Modes:"
        echo "  docker        Use Docker Compose (default)"
        echo "  k8s           Use Kubernetes (kubectl)"
        echo ""
        echo "Examples:"
        echo "  $0                # Docker Compose up"
        echo "  $0 k8s            # Kubernetes deploy"
        echo "  $0 stop           # Docker Compose down"
        echo "  $0 stop k8s       # Kubernetes remove"
        echo "  $0 status         # Check Docker services"
        echo "  $0 status k8s     # Check K8s pods"
        exit 1
        ;;
esac
