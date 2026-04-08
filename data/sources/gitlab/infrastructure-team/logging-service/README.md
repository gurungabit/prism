# logging-service

Owned by: Infrastructure Team

Centralized logging with ELK stack. Log aggregation and search.

## Tech Stack

- Node.js
- Kubernetes
- Go
- React

## Dependencies

None

## Getting Started

```bash
docker compose up logging-service
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
