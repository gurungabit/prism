# admin-dashboard

Owned by: Frontend Team

Internal admin tool for customer support and operations teams.

## Tech Stack

- PostgreSQL
- Redis
- Kafka
- Python

## Dependencies

- api-gateway

## Getting Started

```bash
docker compose up admin-dashboard
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
