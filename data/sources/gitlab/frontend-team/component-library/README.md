# component-library

Owned by: Frontend Team

Shared UI component library used across all frontend applications.

## Tech Stack

- OAuth2
- GraphQL
- Docker
- OpenTelemetry

## Dependencies

None

## Getting Started

```bash
docker compose up component-library
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
