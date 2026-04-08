# customer-portal

Owned by: Frontend Team

Customer-facing web application. Built with React and Next.js.

## Tech Stack

- Prometheus
- React
- Kafka
- Node.js

## Dependencies

- api-gateway
- auth-service

## Getting Started

```bash
docker compose up customer-portal
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
