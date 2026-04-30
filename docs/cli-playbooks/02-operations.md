# 02 — Operations

Day-to-day operational tasks for the Fargate platform.

## Shared variables

These are used throughout — set them once per session:

```bash
CLUSTER=$(aws ssm get-parameter \
  --name /ops-lab/fargate/cluster-name \
  --query Parameter.Value --output text)

SERVICE=$(aws ssm get-parameter \
  --name /ops-lab/fargate/service-name \
  --query Parameter.Value --output text)

ALB_DNS=$(aws ssm get-parameter \
  --name /ops-lab/fargate/alb-dns-name \
  --query Parameter.Value --output text)
```

## Service health

```bash
# Running vs desired task count
aws ecs describe-services \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,status:status}'

# List running tasks
aws ecs list-tasks \
  --cluster "$CLUSTER" \
  --service-name "$SERVICE" \
  --desired-status RUNNING \
  --query taskArns --output table
```

## ECS Exec — interactive shell in a running task

This is the Fargate equivalent of SSM Session Manager on EC2. No SSH, no bastion.

```bash
# Get a task ARN
TASK_ARN=$(aws ecs list-tasks \
  --cluster "$CLUSTER" \
  --service-name "$SERVICE" \
  --desired-status RUNNING \
  --query 'taskArns[0]' --output text)

# Open a shell
aws ecs execute-command \
  --cluster "$CLUSTER" \
  --task "$TASK_ARN" \
  --container app \
  --interactive \
  --command "/bin/sh"
```

## Scaling

```bash
# Scale up manually
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 4

# Scale back to baseline
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 2
```

Auto scaling (CPU and request count) is always active — manual scaling is for overrides only.

## Blue/green deployment via CodeDeploy

Get the CodeDeploy identifiers from stack outputs:

```bash
APP_NAME=$(aws cloudformation describe-stacks \
  --stack-name FargateDeployment-lab \
  --query 'Stacks[0].Outputs[?OutputKey==`CodeDeployApplicationName`].OutputValue' \
  --output text)

DG_NAME=$(aws cloudformation describe-stacks \
  --stack-name FargateDeployment-lab \
  --query 'Stacks[0].Outputs[?OutputKey==`CodeDeployDeploymentGroupName`].OutputValue' \
  --output text)
```

View the current deployment group status:

```bash
aws deploy get-deployment-group \
  --application-name "$APP_NAME" \
  --deployment-group-name "$DG_NAME" \
  --query 'deploymentGroupInfo.{status:deploymentGroupInfo.status,lastAttemptedDeployment:lastAttemptedDeployment}'
```

List recent deployments:

```bash
aws deploy list-deployments \
  --application-name "$APP_NAME" \
  --deployment-group-name "$DG_NAME" \
  --query deploymentsList \
  --output table
```

Stop a deployment (triggers rollback):

```bash
aws deploy stop-deployment \
  --deployment-id <deployment-id> \
  --auto-rollback-enabled
```

## Forced rollback

If the active deployment is in alarm state, CodeDeploy rolls back automatically. To force a manual rollback to the previous task definition:

```bash
# Get the previous task definition ARN from the stopped deployment
aws deploy get-deployment --deployment-id <deployment-id> \
  --query 'deploymentInfo.previousRevision'
```

## Break/fix lab — failure mode injection

The failure mode SSM parameter lets you simulate application faults without redeploying:

```bash
# Current mode
aws ssm get-parameter \
  --name /ops-lab/fargate/failure-mode \
  --query Parameter.Value --output text

# Inject a fault (triggers 500s on /db endpoint)
aws ssm put-parameter \
  --name /ops-lab/fargate/failure-mode \
  --value "db-error" \
  --overwrite

# Restore
aws ssm put-parameter \
  --name /ops-lab/fargate/failure-mode \
  --value "none" \
  --overwrite
```

## Tear down

```bash
cd infra
poetry run cdk destroy --all
```

Aurora and the ECR repo are set to `RETAIN` in non-dev environments — delete them manually from the console after stack deletion if required.
