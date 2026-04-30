# 03 — Observability

Metrics, logs, traces, and alarms for the Fargate platform.

## CloudWatch dashboard

```bash
REGION=ap-southeast-2

# Open in browser (WSL)
explorer.exe "https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards:name=ops-lab-fargate-lab"
```

Panels: ALB request count, 5xx rate, response time p95 · ECS CPU and memory · Aurora connections and CPU · WAF blocked requests.

## Container Insights

Container Insights is enabled on the ECS cluster. Metrics are in the `ECS/ContainerInsights` namespace.

```bash
# CPU utilisation for the service (last hour)
aws cloudwatch get-metric-statistics \
  --namespace ECS/ContainerInsights \
  --metric-name CpuUtilized \
  --dimensions Name=ServiceName,Value=ops-lab-fargate-service-lab \
               Name=ClusterName,Value=ops-lab-fargate-cluster-lab \
  --start-time "$(date -u -d '1 hour ago' +%FT%TZ)" \
  --end-time "$(date -u +%FT%TZ)" \
  --period 300 \
  --statistics Average \
  --query 'Datapoints[*].{time:Timestamp,avg:Average}' \
  --output table

# Memory utilisation
aws cloudwatch get-metric-statistics \
  --namespace ECS/ContainerInsights \
  --metric-name MemoryUtilized \
  --dimensions Name=ServiceName,Value=ops-lab-fargate-service-lab \
               Name=ClusterName,Value=ops-lab-fargate-cluster-lab \
  --start-time "$(date -u -d '1 hour ago' +%FT%TZ)" \
  --end-time "$(date -u +%FT%TZ)" \
  --period 300 \
  --statistics Average \
  --query 'Datapoints[*].{time:Timestamp,avg:Average}' \
  --output table
```

## CloudWatch Logs Insights

Log group: `/ops-lab/fargate/app`

**All errors in the last hour:**

```
fields @timestamp, requestId, path, status, errorType, latencyMs
| filter ispresent(errorType)
| sort @timestamp desc
| limit 100
```

**Slow requests (> 1s):**

```
fields @timestamp, requestId, path, status, latencyMs
| filter latencyMs > 1000
| sort latencyMs desc
| limit 100
```

**5xx responses:**

```
fields @timestamp, requestId, path, status, errorType, latencyMs
| filter status >= 500
| sort @timestamp desc
| limit 100
```

**Request volume by path:**

```
stats count() by path
| sort count desc
```

Run a query via CLI:

```bash
QUERY_ID=$(aws logs start-query \
  --log-group-name /ops-lab/fargate/app \
  --start-time "$(date -d '1 hour ago' +%s)" \
  --end-time "$(date +%s)" \
  --query-string 'fields @timestamp, path, status, latencyMs | filter status >= 500 | sort @timestamp desc | limit 20' \
  --query queryId --output text)

# Wait a moment, then fetch results
aws logs get-query-results --query-id "$QUERY_ID"
```

## Alarms

```bash
# List all Fargate platform alarms and their states
aws cloudwatch describe-alarms \
  --alarm-name-prefix "ops-lab-fargate-" \
  --query 'MetricAlarms[*].{name:AlarmName,state:StateValue,reason:StateReason}' \
  --output table
```

Alarms are wired to `/ops-lab/shared/sns-topic-arn` (the shared ops-lab SNS topic from aws-ops-observability). Any alarm breach sends a notification to whoever is subscribed there.

| Alarm | Threshold | Action |
|---|---|---|
| `ops-lab-fargate-alb-5xx-lab` | >1% 5xx rate (5 min) | SNS |
| `ops-lab-fargate-alb-response-time-lab` | p95 > 2s (10 min) | SNS |
| `ops-lab-fargate-alb-unhealthy-targets-lab` | >0 unhealthy hosts (10 min) | SNS |
| `ops-lab-fargate-ecs-task-count-lab` | <1 running task (10 min) | SNS |
| `ops-lab-fargate-ecs-cpu-lab` | >80% CPU (15 min) | SNS |
| `ops-lab-fargate-ecs-memory-lab` | >80% memory (15 min) | SNS |
| `ops-lab-fargate-rds-cpu-lab` | >80% CPU (15 min) | SNS |
| `ops-lab-fargate-rds-connections-lab` | >80 connections (10 min) | SNS |
| `ops-lab-fargate-waf-blocked-lab` | >100 blocked (5 min) | SNS |

## X-Ray traces

```bash
# Fetch a trace summary for the last 15 minutes
aws xray get-trace-summaries \
  --start-time "$(date -d '15 minutes ago' +%s)" \
  --end-time "$(date +%s)" \
  --query 'TraceSummaries[*].{id:Id,duration:Duration,error:HasError,fault:HasFault}' \
  --output table
```

View the service map in the console:

```bash
REGION=ap-southeast-2
explorer.exe "https://$REGION.console.aws.amazon.com/xray/home?region=$REGION#/service-map"
```

## ALB access logs

ALB logs are written to S3. The bucket name is in the `FargateCompute-lab` stack outputs.

```bash
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name FargateCompute-lab \
  --query 'Stacks[0].Outputs[?contains(OutputKey,`LoggingBucket`)].OutputValue' \
  --output text)

# List recent log files
aws s3 ls "s3://$BUCKET/alb-logs/lab/" --recursive | tail -20

# Download and inspect
aws s3 cp "s3://$BUCKET/alb-logs/lab/<log-file>" - | zcat | head -50
```
