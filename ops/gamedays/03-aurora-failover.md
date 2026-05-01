# Game Day: Aurora Failover

FIS forces an Aurora writer/reader failover. Tests that the URL shortener
recovers automatically — `POST /shorten` and `GET /{code}` will return 500s
for ~30s during the failover window, then self-heal without a task restart.
`GET /healthz` and `GET /` are unaffected (no DB call).

## Prerequisites

- Stack deployed and healthy: `python scripts/verify_fargate.py`
- Aurora engine (`dbEngine=aurora-postgres`, the default)
- FIS stack deployed

## Failure Injection

```bash
ENV=lab

TMPL=$(aws fis list-experiment-templates --region ap-southeast-2 \
  --query "experimentTemplates[?tags.Name=='ops-lab-fargate-aurora-failover-${ENV}'].id" \
  --output text)

EXP=$(aws fis start-experiment --region ap-southeast-2 \
  --experiment-template-id "$TMPL" --query 'experiment.id' --output text)
echo "Experiment ID: $EXP"
```

## What to Watch

```bash
ENV=lab

# Hit /shorten continuously — watch for ~30s of 500s then recovery
while true; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://<ALB_DNS>/shorten" \
    -H "Content-Type: application/json" \
    -d '{"url":"https://aws.amazon.com"}')
  echo "$(date +%H:%M:%S)  $STATUS"
  sleep 2
done

# Aurora cluster state
watch -n5 "aws rds describe-db-clusters --region ap-southeast-2 \
  --db-cluster-identifier ops-lab-fargate-aurora-${ENV} \
  --query 'DBClusters[0].{Status:Status,Members:DBClusterMembers[*].{id:DBInstanceIdentifier,writer:IsClusterWriter}}'"
```

## Expected Behaviour

1. FIS initiates failover; Aurora promotes the reader to writer (~10-30s)
2. `POST /shorten` and `GET /{code}` return 500 during the transition
3. App reconnects via `get_conn()` on the next request — no restart needed
4. Full recovery without operator action

## Application Logs

```bash
aws logs filter-log-events --region ap-southeast-2 \
  --log-group-name /ops-lab/fargate/app \
  --start-time $(date -d '15 minutes ago' +%s)000 \
  --filter-pattern '"Shorten failed"'
```

## Recovery Check

```bash
python scripts/verify_fargate.py
```
