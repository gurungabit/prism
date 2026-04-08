# cdn-manager

Owned by: Infrastructure Team

CDN configuration and cache invalidation management.

## Tech Stack

- Kubernetes
- Go
- Prometheus
- OpenTelemetry

## Dependencies

None

## Getting Started

```bash
docker compose up cdn-manager
```

## API Endpoints

- `GET /health` - Health check
- `GET /api/v1/...` - Main API
- `POST /api/v1/...` - Create/update operations

## Configuration

Environment variables:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `LOG_LEVEL` - Logging level (default: INFO)
