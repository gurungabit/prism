# push-notification-service

Owned by: Mobile Team

Push notification delivery via FCM and APNs.

## Tech Stack

- TypeScript
- OAuth2
- REST
- gRPC

## Dependencies

None

## Getting Started

```bash
docker compose up push-notification-service
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
