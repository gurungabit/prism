# analytics-pipeline

Owned by: Data Team

Real-time event processing pipeline. Ingests clickstream and business events.

## Tech Stack

- OAuth2
- Go
- OpenTelemetry
- Node.js

## Dependencies

- data-warehouse

## Getting Started

```bash
docker compose up analytics-pipeline
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
