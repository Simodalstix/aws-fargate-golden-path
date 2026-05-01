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

## 5. Build, push, and deploy

Run from the repo root. The script handles ECR auth, docker build/push, and
triggers a CodeDeploy blue/green deployment:

```bash
cd ..   # repo root
python scripts/build_and_push.py
```

To push without deploying (e.g. to stage an image first):

```bash
python scripts/build_and_push.py --no-deploy
```

To tag with a specific version instead of `latest`:

```bash
python scripts/build_and_push.py --tag v1.2.3
```

## 6. Verify deployment

```bash
python scripts/verify_fargate.py
```

Expected output ends with `ALL CHECKS PASSED`. The script confirms SSM
outputs exist, ECS tasks are running at desired count, ALB returns 200 on
`/healthz`, and a live `POST /shorten` round-trip succeeds.
