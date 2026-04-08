# reporting-service

Owned by: Data Team

Business reporting and dashboards. Generates scheduled and ad-hoc reports.

## Tech Stack

- JWT
- PostgreSQL
- React
- Python

## Dependencies

- data-warehouse

## Getting Started

```bash
docker compose up reporting-service
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
