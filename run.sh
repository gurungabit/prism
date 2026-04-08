#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/ui"
DATA_DIR="$ROOT_DIR/data/sources"

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

step "Starting infrastructure (OpenSearch, Neo4j, PostgreSQL, Redis)"
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d opensearch neo4j postgres redis 2>&1 | grep -v "^$"

step "Waiting for services to be healthy"
wait_for_http localhost 9200 "OpenSearch"
wait_for_tcp  localhost 5432 "PostgreSQL" 20
wait_for_tcp  localhost 6379 "Redis" 10
wait_for_http localhost 7474 "Neo4j" 30

step "Setting up OpenSearch index + search pipeline"
(cd "$BACKEND_DIR" && uv run python "$ROOT_DIR/scripts/setup_opensearch.py")
ok "OpenSearch configured"

step "Setting up Neo4j schema"
(cd "$BACKEND_DIR" && uv run python "$ROOT_DIR/scripts/setup_neo4j.py")
ok "Neo4j configured"

if [ -z "$(ls -A "$DATA_DIR/gitlab" 2>/dev/null)" ]; then
    step "Generating seed data (first run)"
    (cd "$BACKEND_DIR" && uv run python "$ROOT_DIR/scripts/seed_data.py" "$DATA_DIR")
    ok "186 documents generated across 4 platforms"
else
    ok "Seed data already exists — skipping generation"
fi

step "Ingesting documents into OpenSearch + Neo4j"
(cd "$BACKEND_DIR" && uv run python "$ROOT_DIR/scripts/ingest.py" --data-dir "$ROOT_DIR/data")
ok "Ingestion complete"

set +e
trap cleanup INT TERM

lsof -ti :8000,:5173 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

step "Starting PRISM API (port 8000)"
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
echo -e "  Neo4j:      ${CYAN}http://localhost:7474${NC}"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop everything"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

wait
