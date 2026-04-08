# vault-service

Owned by: Security Team

Secrets management service. Wraps HashiCorp Vault for application-level secret access.

## Tech Stack

- PostgreSQL
- Redis
- GraphQL
- OAuth2

## Dependencies

None

## Getting Started

```bash
docker compose up vault-service
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
