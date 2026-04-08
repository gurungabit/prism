# cert-manager

Owned by: Security Team

TLS certificate management and rotation. Integrates with Let's Encrypt and internal CA.

## Tech Stack

- OAuth2
- GraphQL
- Kubernetes
- Node.js

## Dependencies

None

## Getting Started

```bash
docker compose up cert-manager
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
