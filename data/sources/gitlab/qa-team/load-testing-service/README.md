# load-testing-service

Owned by: QA Team

Performance testing infrastructure. k6-based load testing.

## Tech Stack

- Python
- OpenTelemetry
- Kubernetes
- OAuth2

## Dependencies

- api-gateway

## Getting Started

```bash
docker compose up load-testing-service
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
