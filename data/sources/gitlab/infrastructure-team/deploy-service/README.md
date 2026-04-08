# deploy-service

Owned by: Infrastructure Team

CI/CD orchestration. Manages deployments across environments.

## Tech Stack

- React
- Python
- PostgreSQL
- Go

## Dependencies

- config-service

## Getting Started

```bash
docker compose up deploy-service
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
