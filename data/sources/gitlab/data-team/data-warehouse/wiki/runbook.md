# data-warehouse Runbook

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
kubectl rollout restart deployment/data-warehouse -n production
```
