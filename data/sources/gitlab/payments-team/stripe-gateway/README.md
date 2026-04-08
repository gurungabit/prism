# stripe-gateway

Owned by: Payments Team

Integration layer with Stripe API. Handles webhooks and payment intent flows.

## Tech Stack

- Prometheus
- Node.js
- Python
- Docker

## Dependencies

None

## Getting Started

```bash
docker compose up stripe-gateway
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
