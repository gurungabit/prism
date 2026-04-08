# test-framework

Owned by: QA Team

Shared testing utilities and fixtures used across all services.

## Tech Stack

- GraphQL
- Prometheus
- Node.js
- Kafka

## Dependencies

None

## Getting Started

```bash
docker compose up test-framework
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
