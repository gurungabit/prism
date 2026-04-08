# api-gateway

Owned by: Platform Team

Central entry point for all API requests. Handles routing, rate limiting, and request transformation.

## Tech Stack

- PostgreSQL
- gRPC
- Terraform
- REST

## Dependencies

- auth-service

## Getting Started

```bash
docker compose up api-gateway
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
