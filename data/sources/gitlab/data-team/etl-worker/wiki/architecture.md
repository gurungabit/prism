# etl-worker Architecture

## Overview

ETL workers for data transformation. Runs on scheduled basis via Airflow.

## Component Diagram

The service follows a layered architecture:
- API Layer (FastAPI/Express handlers)
- Business Logic Layer
- Data Access Layer (Repository pattern)
- External Integration Layer

## Data Flow

1. Request arrives at API Gateway
2. Auth middleware validates JWT token
3. Request routed to etl-worker
4. Business logic processes request
5. Database operations via repository
6. Response returned through gateway

## Deployment

- Deployed on Kubernetes (EKS)
- 3 replicas minimum in production
- Rolling deployment strategy
- Health checks on /health endpoint

## Team: Data Team

This service is maintained by the Data Team. For questions, reach out via #team-data-team Slack channel.
