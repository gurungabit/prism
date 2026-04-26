#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/ui"

# --clean wipes every docker-compose volume (Postgres, OpenSearch, Redis)
# before bringing services back up, so the app boots from an empty
# database. Useful when iterating on schema changes that shouldn't be
# bridged with ALTER TABLE migrations.
CLEAN=0
for arg in "$@"; do
    case "$arg" in
        --clean)
            CLEAN=1
            ;;
        *)
            echo "Unknown arg: $arg" >&2
            echo "Usage: $0 [--clean]" >&2
            exit 1
            ;;
    esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${CYAN}▸ $1${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

API_PID=""
UI_PID=""

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
    [ -n "$UI_PID" ] && kill "$UI_PID" 2>/dev/null || true
    lsof -ti :8000,:5173 2>/dev/null | xargs kill -9 2>/dev/null || true
}

wait_for_http() {
    local host=$1 port=$2 name=$3 max=${4:-30}
    local path=${5:-/}
    for i in $(seq 1 "$max"); do
        if curl -sf "http://${host}:${port}${path}" >/dev/null 2>&1; then
            ok "$name ready"
            return 0
        fi
        sleep 2
    done
    fail "$name not reachable on port $port after $((max * 2))s"
}

wait_for_tcp() {
    local host=$1 port=$2 name=$3 max=${4:-30}
    for i in $(seq 1 "$max"); do
        if nc -z "$host" "$port" 2>/dev/null; then
            ok "$name ready"
            return 0
        fi
        sleep 2
    done
    fail "$name not reachable on port $port after $((max * 2))s"
}

echo -e "${CYAN}"
echo "  ██████╗ ██████╗ ██╗███████╗███╗   ███╗"
echo "  ██╔══██╗██╔══██╗██║██╔════╝████╗ ████║"
echo "  ██████╔╝██████╔╝██║███████╗██╔████╔██║"
echo "  ██╔═══╝ ██╔══██╗██║╚════██║██║╚██╔╝██║"
echo "  ██║     ██║  ██║██║███████║██║ ╚═╝ ██║"
echo "  ╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝╚═╝     ╚═╝"
echo -e "${NC}"
echo "  Requirement Intelligence & Service Mapping"
echo ""

command -v uv   >/dev/null 2>&1 || fail "uv not found — install: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v bun  >/dev/null 2>&1 || fail "bun not found — install: curl -fsSL https://bun.sh/install | bash"
command -v docker >/dev/null 2>&1 || fail "docker not found — install Docker Desktop"

step "Installing backend dependencies"
(cd "$BACKEND_DIR" && uv sync --quiet)
ok "Python packages installed"

step "Installing frontend dependencies"
(cd "$FRONTEND_DIR" && bun install --silent)
ok "Frontend packages installed"

if [ "$CLEAN" -eq 1 ]; then
    step "Cleaning infrastructure volumes (--clean requested)"
    docker compose -f "$ROOT_DIR/docker-compose.yml" down -v 2>&1 | grep -v "^$" || true
    ok "Volumes wiped"
fi

step "Starting infrastructure (OpenSearch, PostgreSQL, Redis)"
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d opensearch postgres redis 2>&1 | grep -v "^$"

step "Waiting for services to be healthy"
wait_for_http localhost 9200 "OpenSearch"
wait_for_tcp  localhost 5432 "PostgreSQL" 20
wait_for_tcp  localhost 6379 "Redis" 10

step "Setting up OpenSearch index + search pipeline"
(cd "$BACKEND_DIR" && uv run python "$ROOT_DIR/scripts/setup_opensearch.py")
ok "OpenSearch configured"

# Note: no seed-data generation or automatic ingestion.
# Declarative ownership (see plan.md) means the user tells PRISM about their
# org/teams/services/sources via the setup wizard, and ingestion runs per
# declared source. See /setup on first boot.

set +e
trap cleanup INT TERM

lsof -ti :8000,:5173 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

step "Starting PRISM API (port 8000)"
# ``settings.local_source_root`` defaults to the relative ``./data``,
# which resolves against the process cwd. Without an explicit export,
# starting uvicorn after ``cd backend`` would jail path-based connectors
# at ``backend/data`` -- not the top-level ``data/`` the repo tree and
# docs point users at. Pin the jail to the repo root so the local
# script and docs agree.
mkdir -p "$ROOT_DIR/data"
export PRISM_LOCAL_SOURCE_ROOT="${PRISM_LOCAL_SOURCE_ROOT:-$ROOT_DIR/data}"
cd "$BACKEND_DIR"
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level warning &
API_PID=$!
wait_for_http localhost 8000 "API" 20 "/api/health"

step "Starting PRISM UI (port 5173)"
cd "$FRONTEND_DIR"
    bun run vite --host 0.0.0.0 --port 5173 &
UI_PID=$!
sleep 3

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  PRISM is running!${NC}"
echo ""
echo -e "  UI:         ${CYAN}http://localhost:5173${NC}"
echo -e "  API:        ${CYAN}http://localhost:8000${NC}"
echo -e "  API docs:   ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  OpenSearch: ${CYAN}http://localhost:9200${NC}"
echo ""
echo -e "  First run? Head to ${CYAN}http://localhost:5173/setup${NC} to declare your org."
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop everything"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

wait
