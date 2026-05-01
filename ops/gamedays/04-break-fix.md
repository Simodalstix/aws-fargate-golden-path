# Game Day: Break/Fix — Injected 500 Errors

Setting the SSM failure-mode parameter to `return_500` causes every task
to return HTTP 500 on all requests — including `/healthz`. The ALB marks
all targets unhealthy and the 5xx alarm fires. Fix is a single SSM reset;
no redeployment required.

This is the equivalent of the unhealthy-targets scenario from the EC2 fleet:
same detection path (alarm → runbook), different failure mechanism
(SSM parameter vs instance failure).

## Prerequisites

- Stack deployed and healthy: `python scripts/verify_fargate.py`

## Failure Injection

```bash
aws ssm put-parameter --region ap-southeast-2 \
  --name /ops-lab/fargate/failure-mode \
  --value return_500 \
  --type String \
  --overwrite
```

The app polls SSM every 5 seconds — impact begins within one polling cycle.

## What to Watch

```bash
ENV=lab

# Continuous health probe
while true; do
  echo "$(date +%H:%M:%S)  $(curl -s -o /dev/null -w '%{http_code}' http://<ALB_DNS>/healthz)"
  sleep 2
done

# ALB 5xx alarm (expect ALARM within 2-3 min)
watch -n15 "aws cloudwatch describe-alarms --region ap-southeast-2 \
  --alarm-names 'ops-lab-fargate-alb-5xx-${ENV}' \
  --query 'MetricAlarms[0].StateValue'"

# Target health
aws elbv2 describe-target-health --region ap-southeast-2 \
  --target-group-arn $(aws elbv2 describe-target-groups --region ap-southeast-2 \
    --names "ops-lab-fargate-tg1-${ENV}" \
    --query 'TargetGroups[0].TargetGroupArn' --output text)
```

## Resolution

```bash
# Reset — no redeployment needed
aws ssm put-parameter --region ap-southeast-2 \
  --name /ops-lab/fargate/failure-mode \
  --value none \
  --type String \
  --overwrite
```

Tasks pick up the change within 5s. Targets return healthy after two
consecutive passing health checks (~60s with the 30s interval).

## Recovery Check

```bash
python scripts/verify_fargate.py
```

## Cleanup Verification

```bash
aws ssm get-parameter --region ap-southeast-2 \
  --name /ops-lab/fargate/failure-mode \
  --query 'Parameter.Value'
# Should return: "none"
```
