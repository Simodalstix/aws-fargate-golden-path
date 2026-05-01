# Game Day: CPU Stress / Autoscaling

FIS injects 80% CPU stress into one Fargate task for 10 minutes. Tests that
the CloudWatch CPU alarm fires and the autoscaling policy adds tasks.

## Prerequisites

- Stack deployed and healthy: `python scripts/verify_fargate.py`
- FIS stack deployed

## Failure Injection

```bash
ENV=lab

TMPL=$(aws fis list-experiment-templates --region ap-southeast-2 \
  --query "experimentTemplates[?tags.Name=='ops-lab-fargate-ecs-cpu-stress-${ENV}'].id" \
  --output text)

EXP=$(aws fis start-experiment --region ap-southeast-2 \
  --experiment-template-id "$TMPL" --query 'experiment.id' --output text)
echo "Experiment ID: $EXP"
```

## What to Watch

```bash
ENV=lab

# CPU alarm (expect ALARM within 2-5 min)
watch -n15 "aws cloudwatch describe-alarms --region ap-southeast-2 \
  --alarm-names 'ops-lab-fargate-ecs-cpu-${ENV}' \
  --query 'MetricAlarms[0].StateValue'"

# Task count (expect scale-out as alarm triggers)
watch -n15 "aws ecs describe-services --region ap-southeast-2 \
  --cluster ops-lab-fargate-cluster-${ENV} \
  --services ops-lab-fargate-service-${ENV} \
  --query 'services[0].{desired:desiredCount,running:runningCount}'"

# Autoscaling activity log
aws application-autoscaling describe-scaling-activities \
  --region ap-southeast-2 --service-namespace ecs \
  --resource-id "service/ops-lab-fargate-cluster-${ENV}/ops-lab-fargate-service-${ENV}"
```

## Expected Behaviour

1. CPU stress raises utilisation above the 70% target on the affected task
2. CloudWatch alarm fires within ~2 min
3. Autoscaling adds tasks (scale-out cooldown: 2 min)
4. Experiment ends at 10 min; CPU returns to baseline
5. Service scales back in after the 5 min scale-in cooldown

## Recovery Check

```bash
# Alarm should return to OK ~5 min after experiment ends
aws cloudwatch describe-alarms --region ap-southeast-2 \
  --alarm-names "ops-lab-fargate-ecs-cpu-${ENV}" \
  --query 'MetricAlarms[0].StateValue'
```
