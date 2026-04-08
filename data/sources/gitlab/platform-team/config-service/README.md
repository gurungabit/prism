# config-service

Owned by: Platform Team

Centralized configuration management. Provides runtime config to all services via gRPC.

## Tech Stack

- OAuth2
- TypeScript
- Prometheus
- REST

## Dependencies

None

## Getting Started

```bash
docker compose up config-service
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
