# etl-worker

Owned by: Data Team

ETL workers for data transformation. Runs on scheduled basis via Airflow.

## Tech Stack

- Prometheus
- Kafka
- TypeScript
- React

## Dependencies

- analytics-pipeline

## Getting Started

```bash
docker compose up etl-worker
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
