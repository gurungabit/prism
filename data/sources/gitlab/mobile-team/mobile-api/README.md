# mobile-api

Owned by: Mobile Team

Backend-for-frontend optimized for mobile clients. Aggregates multiple service calls.

## Tech Stack

- OAuth2
- REST
- Python
- Terraform

## Dependencies

- api-gateway
- push-notification-service

## Getting Started

```bash
docker compose up mobile-api
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
