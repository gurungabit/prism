# audit-service

Owned by: Security Team

Records security-relevant events for compliance. Immutable audit trail.

## Tech Stack

- Kafka
- TypeScript
- PostgreSQL
- gRPC

## Dependencies

None

## Getting Started

```bash
docker compose up audit-service
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
