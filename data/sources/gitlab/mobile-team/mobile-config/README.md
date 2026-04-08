# mobile-config

Owned by: Mobile Team

Feature flags and configuration for mobile apps. Supports A/B testing.

## Tech Stack

- TypeScript
- OAuth2
- Docker
- OpenTelemetry

## Dependencies

None

## Getting Started

```bash
docker compose up mobile-config
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
