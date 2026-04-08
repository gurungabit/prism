#!/usr/bin/env python3
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

TEAMS = [
    {
        "name": "Platform Team",
        "services": ["auth-service", "api-gateway", "config-service", "user-service"],
    },
    {
        "name": "Security Team",
        "services": ["vault-service", "cert-manager", "audit-service"],
    },
    {
        "name": "Payments Team",
        "services": [
            "payment-processor",
            "billing-service",
            "invoice-service",
            "stripe-gateway",
        ],
    },
    {
        "name": "Frontend Team",
        "services": ["customer-portal", "admin-dashboard", "component-library"],
    },
    {
        "name": "Data Team",
        "services": [
            "analytics-pipeline",
            "data-warehouse",
            "reporting-service",
            "etl-worker",
        ],
    },
    {
        "name": "Mobile Team",
        "services": ["mobile-api", "push-notification-service", "mobile-config"],
    },
    {
        "name": "Infrastructure Team",
        "services": [
            "deploy-service",
            "monitoring-stack",
            "logging-service",
            "cdn-manager",
        ],
    },
    {"name": "QA Team", "services": ["test-framework", "load-testing-service"]},
]

TECHNOLOGIES = [
    "Python",
    "TypeScript",
    "Go",
    "PostgreSQL",
    "Redis",
    "Kafka",
    "Docker",
    "Kubernetes",
    "Terraform",
    "React",
    "Node.js",
    "gRPC",
    "GraphQL",
    "REST",
    "JWT",
    "OAuth2",
    "OpenTelemetry",
    "Prometheus",
]

DEPENDENCIES = [
    ("auth-service", "user-service"),
    ("auth-service", "vault-service"),
    ("api-gateway", "auth-service"),
    ("customer-portal", "api-gateway"),
    ("customer-portal", "auth-service"),
    ("admin-dashboard", "api-gateway"),
    ("payment-processor", "stripe-gateway"),
    ("payment-processor", "auth-service"),
    ("billing-service", "payment-processor"),
    ("invoice-service", "billing-service"),
    ("analytics-pipeline", "data-warehouse"),
    ("reporting-service", "data-warehouse"),
    ("mobile-api", "api-gateway"),
    ("mobile-api", "push-notification-service"),
    ("deploy-service", "config-service"),
    ("monitoring-stack", "logging-service"),
    ("etl-worker", "analytics-pipeline"),
    ("load-testing-service", "api-gateway"),
]

OWNERSHIP_CONFLICTS = [
    {
        "service": "auth-service",
        "teams": ["Platform Team", "Security Team"],
        "note": "Platform Team owns the code, Security Team reviews and audits",
    },
    {
        "service": "api-gateway",
        "teams": ["Platform Team", "Infrastructure Team"],
        "note": "Shared ownership — Platform owns business logic, Infra owns deployment",
    },
    {
        "service": "customer-portal",
        "teams": ["Frontend Team", "Platform Team"],
        "note": "Frontend owns UI, Platform owns backend-for-frontend",
    },
]


def generate_seed_data(output_dir: str = "data/sources"):
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    _generate_gitlab_data(base / "gitlab")
    _generate_sharepoint_data(base / "sharepoint")
    _generate_excel_data(base / "excel")
    _generate_onenote_data(base / "onenote")

    print(f"Seed data generated in {base}")


def _generate_gitlab_data(base: Path):
    for team in TEAMS:
        team_slug = team["name"].lower().replace(" ", "-")

        for service in team["services"]:
            repo_dir = base / team_slug / service
            repo_dir.mkdir(parents=True, exist_ok=True)

            readme = _gen_readme(service, team["name"])
            (repo_dir / "README.md").write_text(readme)

            wiki_dir = repo_dir / "wiki"
            wiki_dir.mkdir(exist_ok=True)

            arch_doc = _gen_architecture_doc(service, team["name"])
            (wiki_dir / "architecture.md").write_text(arch_doc)

            if random.random() > 0.3:
                runbook = _gen_runbook(service)
                (wiki_dir / "runbook.md").write_text(runbook)

            issues_dir = repo_dir / "issues"
            issues_dir.mkdir(exist_ok=True)
            for i in range(random.randint(2, 5)):
                issue = _gen_issue(service, team["name"], i + 1)
                (issues_dir / f"issue-{i + 1}.json").write_text(
                    json.dumps(issue, indent=2)
                )


def _generate_sharepoint_data(base: Path):
    for team in TEAMS:
        team_slug = team["name"].lower().replace(" ", "-")
        site_dir = base / team_slug
        site_dir.mkdir(parents=True, exist_ok=True)

        charter = _gen_team_charter(team)
        (site_dir / "team-charter.md").write_text(charter)

        onboarding = _gen_onboarding_doc(team)
        (site_dir / "onboarding-guide.md").write_text(onboarding)

        if random.random() > 0.5:
            meeting = _gen_meeting_notes(team)
            (site_dir / "meeting-notes-2025-03.md").write_text(meeting)


def _generate_excel_data(base: Path):
    base.mkdir(parents=True, exist_ok=True)

    import csv

    with open(base / "service-catalog.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Service", "Team", "Status", "Repository", "Language", "Dependencies"]
        )
        for team in TEAMS:
            for service in team["services"]:
                deps = [d[1] for d in DEPENDENCIES if d[0] == service]
                lang = random.choice(["Python", "TypeScript", "Go"])
                writer.writerow(
                    [
                        service,
                        team["name"],
                        "active",
                        f"gitlab/{service}",
                        lang,
                        "; ".join(deps),
                    ]
                )

    with open(base / "team-roster.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Team", "Role", "Email"])
        first_names = [
            "Alice",
            "Bob",
            "Charlie",
            "Diana",
            "Eve",
            "Frank",
            "Grace",
            "Hector",
        ]
        last_names = [
            "Smith",
            "Johnson",
            "Williams",
            "Brown",
            "Jones",
            "Garcia",
            "Miller",
            "Davis",
        ]
        for team in TEAMS:
            for i in range(random.randint(3, 6)):
                fn = random.choice(first_names)
                ln = random.choice(last_names)
                role = random.choice(
                    [
                        "Engineer",
                        "Senior Engineer",
                        "Staff Engineer",
                        "Engineering Manager",
                    ]
                )
                writer.writerow(
                    [
                        f"{fn} {ln}",
                        team["name"],
                        role,
                        f"{fn.lower()}.{ln.lower()}@company.com",
                    ]
                )


def _generate_onenote_data(base: Path):
    engineering_dir = base / "engineering-notebook" / "architecture-decisions"
    engineering_dir.mkdir(parents=True, exist_ok=True)

    (engineering_dir / "adr-001-auth-approach.html").write_text(
        _gen_adr_html(
            "Authentication Approach",
            "Use JWT with short-lived access tokens and httpOnly refresh tokens",
            "auth-service",
            "Platform Team",
        )
    )
    (engineering_dir / "adr-002-api-gateway.html").write_text(
        _gen_adr_html(
            "API Gateway Selection",
            "Use custom Go-based gateway over Kong for better control",
            "api-gateway",
            "Infrastructure Team",
        )
    )

    incidents_dir = base / "engineering-notebook" / "incidents"
    incidents_dir.mkdir(parents=True, exist_ok=True)

    (incidents_dir / "incident-2025-02-auth-outage.html").write_text(
        _gen_incident_html(
            "Auth Service Outage",
            "auth-service",
            "JWT validation cache expired during deploy",
        )
    )


def _gen_readme(service: str, team: str) -> str:
    deps = [d[1] for d in DEPENDENCIES if d[0] == service]
    techs = random.sample(TECHNOLOGIES, min(4, len(TECHNOLOGIES)))
    dep_text = "\n".join(f"- {d}" for d in deps) if deps else "None"

    return f"""# {service}

Owned by: {team}

{_gen_service_description(service)}

## Tech Stack

{chr(10).join(f"- {t}" for t in techs)}

## Dependencies

{dep_text}

## Getting Started

```bash
docker compose up {service}
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
"""


def _gen_architecture_doc(service: str, team: str) -> str:
    return f"""# {service} Architecture

## Overview

{_gen_service_description(service)}

## Component Diagram

The service follows a layered architecture:
- API Layer (FastAPI/Express handlers)
- Business Logic Layer
- Data Access Layer (Repository pattern)
- External Integration Layer

## Data Flow

1. Request arrives at API Gateway
2. Auth middleware validates JWT token
3. Request routed to {service}
4. Business logic processes request
5. Database operations via repository
6. Response returned through gateway

## Deployment

- Deployed on Kubernetes (EKS)
- 3 replicas minimum in production
- Rolling deployment strategy
- Health checks on /health endpoint

## Team: {team}

This service is maintained by the {team}. For questions, reach out via #team-{team.lower().replace(" ", "-")} Slack channel.
"""


def _gen_runbook(service: str) -> str:
    return f"""# {service} Runbook

## Common Issues

### High Latency
1. Check database connection pool utilization
2. Review recent deployments for regressions
3. Check downstream service health

### Out of Memory
1. Check for memory leaks in recent releases
2. Increase pod memory limits temporarily
3. Restart affected pods

### Authentication Failures
1. Verify JWT signing keys are current
2. Check auth-service health
3. Verify token expiration settings

## Escalation Path

1. On-call engineer (PagerDuty)
2. Team lead
3. Engineering manager

## Recovery Procedures

### Database Failover
1. Verify replica health
2. Promote replica if primary is down
3. Update connection strings
4. Notify dependent services

### Complete Service Restart
```bash
kubectl rollout restart deployment/{service} -n production
```
"""


def _gen_issue(service: str, team: str, issue_num: int) -> dict:
    titles = [
        f"Add rate limiting to {service}",
        f"Upgrade {service} dependencies",
        f"Implement health check improvements for {service}",
        f"Add metrics endpoint to {service}",
        f"Refactor {service} error handling",
        f"Add integration tests for {service}",
        f"Optimize {service} database queries",
        f"Add caching layer to {service}",
    ]
    states = ["open", "closed", "open", "closed", "open"]
    labels_pool = ["enhancement", "bug", "tech-debt", "security", "performance"]
    days_ago = random.randint(1, 180)

    return {
        "title": random.choice(titles),
        "body": f"We need to improve {service} by implementing this change. This is part of the {team}'s quarterly goals.",
        "state": random.choice(states),
        "labels": random.sample(labels_pool, random.randint(1, 3)),
        "assignees": [{"name": f"engineer-{random.randint(1, 20)}"}],
        "created_at": (datetime.now() - timedelta(days=days_ago)).isoformat(),
        "updated_at": (
            datetime.now() - timedelta(days=random.randint(0, days_ago))
        ).isoformat(),
    }


def _gen_team_charter(team: dict) -> str:
    return f"""# {team["name"]} Charter

## Mission
The {team["name"]} is responsible for building and maintaining the following services:
{chr(10).join(f"- {s}" for s in team["services"])}

## Responsibilities
- Service reliability and uptime (99.9% SLA)
- Feature development and maintenance
- Security patching and dependency updates
- On-call rotation for owned services

## Team Members
See team-roster.xlsx for current team composition.

## Communication
- Slack: #team-{team["name"].lower().replace(" ", "-")}
- Jira: {team["name"].upper().replace(" ", "_")} board
- Weekly standup: Monday 10:00 AM CT
"""


def _gen_onboarding_doc(team: dict) -> str:
    return f"""# {team["name"]} Onboarding Guide

## Week 1
- Set up development environment
- Read architecture docs for: {", ".join(team["services"][:3])}
- Meet with team lead and mentor

## Week 2
- Pick up a starter task from the backlog
- Review recent PRs to understand code style
- Shadow on-call engineer

## Week 3-4
- Complete first feature/bugfix independently
- Join on-call rotation (shadow first)
- Present work at team demo
"""


def _gen_meeting_notes(team: dict) -> str:
    return f"""# {team["name"]} - Engineering Meeting Notes

## Date: March 15, 2025

### Attendees
- Team lead, 4 engineers

### Discussion Items

1. **Q2 Planning**
   - Priority: Reliability improvements for {team["services"][0]}
   - Secondary: Feature work on {team["services"][1] if len(team["services"]) > 1 else team["services"][0]}

2. **Technical Debt**
   - Need to upgrade dependencies across all services
   - Database migration for {team["services"][0]} pending

3. **Action Items**
   - [ ] Create RFC for {team["services"][0]} redesign
   - [ ] Schedule security review with Security Team
   - [ ] Update runbooks for all services
"""


def _gen_adr_html(title: str, decision: str, service: str, team: str) -> str:
    return f"""<html>
<body>
<h1>ADR: {title}</h1>
<h2>Status: Accepted</h2>
<h2>Context</h2>
<p>The {team} needs to make a decision regarding {title.lower()} for the {service}.</p>
<h2>Decision</h2>
<p>{decision}</p>
<h2>Consequences</h2>
<ul>
<li>Improved security posture</li>
<li>Better performance characteristics</li>
<li>Team needs training on new approach</li>
</ul>
<h2>Service: {service}</h2>
<h2>Team: {team}</h2>
</body>
</html>"""


def _gen_incident_html(title: str, service: str, root_cause: str) -> str:
    return f"""<html>
<body>
<h1>Incident Report: {title}</h1>
<h2>Date: February 15, 2025</h2>
<h2>Severity: P1</h2>
<h2>Service: {service}</h2>
<h2>Impact</h2>
<p>Users unable to authenticate for 45 minutes during peak hours.</p>
<h2>Root Cause</h2>
<p>{root_cause}</p>
<h2>Timeline</h2>
<ul>
<li>14:00 - Alert triggered for authentication failures</li>
<li>14:05 - On-call engineer acknowledged</li>
<li>14:15 - Root cause identified</li>
<li>14:30 - Fix deployed</li>
<li>14:45 - Service fully recovered</li>
</ul>
<h2>Action Items</h2>
<ul>
<li>Add cache warming during deployments</li>
<li>Improve monitoring for token validation latency</li>
<li>Update runbook with this scenario</li>
</ul>
</body>
</html>"""


def _gen_service_description(service: str) -> str:
    descriptions = {
        "auth-service": "Handles user authentication, JWT token issuance, and session management. Supports SSO via SAML and OAuth2.",
        "api-gateway": "Central entry point for all API requests. Handles routing, rate limiting, and request transformation.",
        "config-service": "Centralized configuration management. Provides runtime config to all services via gRPC.",
        "user-service": "Manages user profiles, preferences, and account settings. Source of truth for user data.",
        "vault-service": "Secrets management service. Wraps HashiCorp Vault for application-level secret access.",
        "cert-manager": "TLS certificate management and rotation. Integrates with Let's Encrypt and internal CA.",
        "audit-service": "Records security-relevant events for compliance. Immutable audit trail.",
        "payment-processor": "Core payment processing. Handles credit card charges, refunds, and payment method management.",
        "billing-service": "Subscription billing, invoicing, and revenue recognition. Generates monthly billing cycles.",
        "invoice-service": "Invoice generation, PDF rendering, and delivery via email/API.",
        "stripe-gateway": "Integration layer with Stripe API. Handles webhooks and payment intent flows.",
        "customer-portal": "Customer-facing web application. Built with React and Next.js.",
        "admin-dashboard": "Internal admin tool for customer support and operations teams.",
        "component-library": "Shared UI component library used across all frontend applications.",
        "analytics-pipeline": "Real-time event processing pipeline. Ingests clickstream and business events.",
        "data-warehouse": "Central data warehouse on PostgreSQL + dbt. Houses all analytical data.",
        "reporting-service": "Business reporting and dashboards. Generates scheduled and ad-hoc reports.",
        "etl-worker": "ETL workers for data transformation. Runs on scheduled basis via Airflow.",
        "mobile-api": "Backend-for-frontend optimized for mobile clients. Aggregates multiple service calls.",
        "push-notification-service": "Push notification delivery via FCM and APNs.",
        "mobile-config": "Feature flags and configuration for mobile apps. Supports A/B testing.",
        "deploy-service": "CI/CD orchestration. Manages deployments across environments.",
        "monitoring-stack": "Observability platform. Prometheus, Grafana, and alerting.",
        "logging-service": "Centralized logging with ELK stack. Log aggregation and search.",
        "cdn-manager": "CDN configuration and cache invalidation management.",
        "test-framework": "Shared testing utilities and fixtures used across all services.",
        "load-testing-service": "Performance testing infrastructure. k6-based load testing.",
    }
    return descriptions.get(
        service,
        f"A microservice that handles {service.replace('-', ' ')} functionality.",
    )


TEST_REQUIREMENTS = [
    {
        "requirement": "Add multi-factor authentication (MFA) to the customer portal",
        "expected_team": "Platform Team",
        "expected_services": ["auth-service", "customer-portal", "user-service"],
        "expected_deps": ["vault-service"],
    },
    {
        "requirement": "Implement a new payment method for cryptocurrency",
        "expected_team": "Payments Team",
        "expected_services": ["payment-processor", "billing-service", "stripe-gateway"],
        "expected_deps": ["auth-service"],
    },
    {
        "requirement": "Add real-time analytics dashboard for customer behavior",
        "expected_team": "Data Team",
        "expected_services": [
            "analytics-pipeline",
            "reporting-service",
            "data-warehouse",
        ],
        "expected_deps": ["customer-portal"],
    },
    {
        "requirement": "Migrate the API gateway from REST to GraphQL",
        "expected_team": "Platform Team",
        "expected_services": ["api-gateway"],
        "expected_deps": ["auth-service", "customer-portal", "mobile-api"],
    },
    {
        "requirement": "Add push notifications for order status updates",
        "expected_team": "Mobile Team",
        "expected_services": ["push-notification-service", "mobile-api"],
        "expected_deps": ["payment-processor", "billing-service"],
    },
]


if __name__ == "__main__":
    import sys

    output = sys.argv[1] if len(sys.argv) > 1 else "data/sources"
    generate_seed_data(output)
    print(f"\nTest requirements for evaluation:")
    for i, tc in enumerate(TEST_REQUIREMENTS, 1):
        print(f"  {i}. {tc['requirement']}")
        print(f"     Expected team: {tc['expected_team']}")
        print(f"     Expected services: {', '.join(tc['expected_services'])}")
