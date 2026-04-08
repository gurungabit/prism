# billing-service

Owned by: Payments Team

Subscription billing, invoicing, and revenue recognition. Generates monthly billing cycles.

## Tech Stack

- PostgreSQL
- REST
- gRPC
- Prometheus

## Dependencies

- payment-processor

## Getting Started

```bash
docker compose up billing-service
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
