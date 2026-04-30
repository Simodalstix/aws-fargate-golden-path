# 01 — Build and Deploy

Deploy the Fargate platform from scratch and push the first container image.

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` returns account `820242933814`)
- Docker running
- Poetry installed (`pip install poetry`)
- [aws-ops-networking](https://github.com/Simodalstix/aws-ops-networking) deployed
- [aws-ops-observability](https://github.com/Simodalstix/aws-ops-observability) deployed

Verify the upstream SSM params exist:

```bash
aws ssm get-parameter --name /ops-lab/networking/vpc-id --query Parameter.Value --output text
aws ssm get-parameter --name /ops-lab/shared/sns-topic-arn --query Parameter.Value --output text
```

## 1. Install dependencies

```bash
cd infra
poetry install
```

## 2. Bootstrap CDK (first time only)

```bash
poetry run cdk bootstrap aws://820242933814/ap-southeast-2
```

## 3. Synthesise and review

```bash
poetry run cdk synth --all
```

Check the output for any context warnings. On first synth, CDK populates `cdk.context.json` with the VPC lookup — this is expected and should be committed.

## 4. Deploy in order

Stacks can be deployed together or individually. Deploy all at once:

```bash
poetry run cdk deploy --all
```

Or deploy individually (useful when iterating on a single stack):

```bash
poetry run cdk deploy FargateData-lab
poetry run cdk deploy FargateCompute-lab
poetry run cdk deploy FargateObservability-lab
poetry run cdk deploy FargateDeployment-lab
```

FIS is disabled by default. To enable:

```bash
poetry run cdk deploy FargateFIS-lab -c enableFIS=true
```

## 5. Build and push the container image

Get the ECR URI from SSM:

```bash
ECR_URI=$(aws ssm get-parameter \
  --name /ops-lab/fargate/ecr-repo-uri \
  --query Parameter.Value --output text)
```

Authenticate Docker to ECR:

```bash
aws ecr get-login-password --region ap-southeast-2 \
  | docker login --username AWS --password-stdin "$ECR_URI"
```

Build, tag, and push:

```bash
docker build -t ops-lab-fargate-app ../app/
docker tag ops-lab-fargate-app:latest "$ECR_URI:latest"
docker push "$ECR_URI:latest"
```

## 6. Trigger a new ECS deployment

After pushing a new image, force a new deployment so ECS pulls it:

```bash
CLUSTER=$(aws ssm get-parameter \
  --name /ops-lab/fargate/cluster-name \
  --query Parameter.Value --output text)

SERVICE=$(aws ssm get-parameter \
  --name /ops-lab/fargate/service-name \
  --query Parameter.Value --output text)

aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --force-new-deployment
```

## 7. Verify deployment

```bash
# Watch service stabilise
aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services "$SERVICE"

# Check running task count
aws ecs describe-services \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount}'

# Hit the ALB
ALB_DNS=$(aws ssm get-parameter \
  --name /ops-lab/fargate/alb-dns-name \
  --query Parameter.Value --output text)

curl -s "http://$ALB_DNS/healthz"
```

Expected: `{"status": "ok"}` with HTTP 200.
