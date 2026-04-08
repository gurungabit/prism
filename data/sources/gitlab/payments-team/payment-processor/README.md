# payment-processor

Owned by: Payments Team

Core payment processing. Handles credit card charges, refunds, and payment method management.

## Tech Stack

- Go
- Prometheus
- Node.js
- Terraform

## Dependencies

- stripe-gateway
- auth-service

## Getting Started

```bash
docker compose up payment-processor
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
