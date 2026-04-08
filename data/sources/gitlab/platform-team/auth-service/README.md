# auth-service

Owned by: Platform Team

Handles user authentication, JWT token issuance, and session management. Supports SSO via SAML and OAuth2.

## Tech Stack

- Redis
- PostgreSQL
- Docker
- Kafka

## Dependencies

- user-service
- vault-service

## Getting Started

```bash
docker compose up auth-service
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
