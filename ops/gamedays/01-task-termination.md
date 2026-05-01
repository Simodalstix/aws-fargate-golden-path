# Game Day: ECS Task Termination

FIS stops 50% of running Fargate tasks. Tests ECS self-healing and confirms
the ALB continues serving traffic while tasks drain and replacements start.

## Prerequisites

- Stack deployed and healthy: `python scripts/verify_fargate.py`
- FIS stack deployed (`cdk deploy FargateFIS-lab --context enableFIS=true`)

## Failure Injection

```bash
ENV=lab

TMPL=$(aws fis list-experiment-templates --region ap-southeast-2 \
  --query "experimentTemplates[?tags.Name=='ops-lab-fargate-ecs-task-termination-${ENV}'].id" \
  --output text)

EXP=$(aws fis start-experiment --region ap-southeast-2 \
  --experiment-template-id "$TMPL" --query 'experiment.id' --output text)
echo "Experiment ID: $EXP"
```

## What to Watch

```bash
# Task count — drops then recovers to desired
watch -n5 "aws ecs describe-services --region ap-southeast-2 \
  --cluster ops-lab-fargate-cluster-${ENV} \
  --services ops-lab-fargate-service-${ENV} \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount}'"

# ALB should stay up throughout (tasks drain before stopping)
while true; do
  echo "$(date +%H:%M:%S)  $(curl -s -o /dev/null -w '%{http_code}' http://<ALB_DNS>/healthz)"
  sleep 3
done
```

## Expected Behaviour

1. FIS stops ~50% of tasks (ECS graceful drain → SIGTERM → stop)
2. ECS scheduler detects count below desired, launches replacements
3. New tasks pass ALB health checks within ~60s (`start_period`)
4. Service back to full desired count within ~2 min

## Recovery Check

```bash
python scripts/verify_fargate.py
```

## Cleanup

```bash
aws fis get-experiment --region ap-southeast-2 --id "$EXP" \
  --query 'experiment.state.status'
```
