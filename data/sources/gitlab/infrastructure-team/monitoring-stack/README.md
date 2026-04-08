# monitoring-stack

Owned by: Infrastructure Team

Observability platform. Prometheus, Grafana, and alerting.

## Tech Stack

- REST
- gRPC
- OpenTelemetry
- Kafka

## Dependencies

- logging-service

## Getting Started

```bash
docker compose up monitoring-stack
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
