# invoice-service

Owned by: Payments Team

Invoice generation, PDF rendering, and delivery via email/API.

## Tech Stack

- TypeScript
- GraphQL
- Go
- React

## Dependencies

- billing-service

## Getting Started

```bash
docker compose up invoice-service
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
