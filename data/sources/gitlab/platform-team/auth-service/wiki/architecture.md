# auth-service Architecture

## Overview

Handles user authentication, JWT token issuance, and session management. Supports SSO via SAML and OAuth2.

## Component Diagram

The service follows a layered architecture:
- API Layer (FastAPI/Express handlers)
- Business Logic Layer
- Data Access Layer (Repository pattern)
- External Integration Layer

## Data Flow

1. Request arrives at API Gateway
2. Auth middleware validates JWT token
3. Request routed to auth-service
4. Business logic processes request
5. Database operations via repository
6. Response returned through gateway

## Deployment

- Deployed on Kubernetes (EKS)
- 3 replicas minimum in production
- Rolling deployment strategy
- Health checks on /health endpoint

## Team: Platform Team

This service is maintained by the Platform Team. For questions, reach out via #team-platform-team Slack channel.
