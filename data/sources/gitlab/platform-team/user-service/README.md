# user-service

Owned by: Platform Team

Manages user profiles, preferences, and account settings. Source of truth for user data.

## Tech Stack

- OpenTelemetry
- REST
- GraphQL
- Go

## Dependencies

None

## Getting Started

```bash
docker compose up user-service
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
