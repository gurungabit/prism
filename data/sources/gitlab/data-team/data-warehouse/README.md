# data-warehouse

Owned by: Data Team

Central data warehouse on PostgreSQL + dbt. Houses all analytical data.

## Tech Stack

- Kubernetes
- Go
- Python
- GraphQL

## Dependencies

None

## Getting Started

```bash
docker compose up data-warehouse
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
