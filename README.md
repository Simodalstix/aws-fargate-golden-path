# aws-fargate-golden-path

[![CDK](https://img.shields.io/badge/CDK-2.180+-orange.svg)](https://github.com/aws/aws-cdk)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Build Status](https://img.shields.io/github/actions/workflow/status/Simodalstix/AWS-fargate-golden-path/ci.yml?branch=main)](https://github.com/Simodalstix/AWS-fargate-golden-path/actions)
[![Release](https://img.shields.io/github/v/release/Simodalstix/AWS-fargate-golden-path?include_prereleases)](https://github.com/Simodalstix/AWS-fargate-golden-path/releases)

A production-style ECS Fargate container platform — the opinionated "golden path" a platform team would hand to application teams. Part of the [ops-lab](https://github.com/Simodalstix) platform series.

**What it demonstrates:** immutable container deployments, blue/green traffic shifting via CodeDeploy, ECS Exec for access (no SSH), Container Insights observability, and chaos engineering via FIS — contrasted directly with the EC2 ASG fleet in [aws-3tier-platform](https://github.com/Simodalstix/aws-3tier-platform).

## Architecture

![ECS Fargate Golden Path Architecture](diagrams/ecs-golden-path-diagram.svg)

_Architecture diagram created using AWS official icons and Excalidraw_

**Platform components:**
- **Shared networking** — VPC and subnets from [aws-ops-networking](https://github.com/Simodalstix/aws-ops-networking) via SSM Parameter Store
- **Shared observability** — SNS alarm topic from [aws-ops-observability](https://github.com/Simodalstix/aws-ops-observability) via SSM Parameter Store
- **ECS Fargate** — tasks in public subnets with public IP, no NAT cost; ECS Exec enabled
- **Aurora Serverless v2** — writer/reader in isolated subnets, Secrets Manager rotation
- **ALB** — public subnets, WAF protection, S3 access logs, blue/green target groups
- **CodeDeploy** — blue/green traffic shifting (canary 10% → 100%), auto-rollback
- **Observability** — Container Insights, CloudWatch alarms wired to shared SNS, X-Ray tracing

## Prerequisites

This project reads from two deployed stacks:

| Dependency | SSM parameters used |
|---|---|
| [aws-ops-networking](https://github.com/Simodalstix/aws-ops-networking) | `/ops-lab/networking/vpc-id`, `/ops-lab/networking/subnet/public-*`, `/ops-lab/networking/subnet/isolated-*` |
| [aws-ops-observability](https://github.com/Simodalstix/aws-ops-observability) | `/ops-lab/shared/sns-topic-arn` |

Deploy those first if they are not already running.

## Quick Start

```bash
# Install dependencies (Poetry)
cd infra && poetry install

# Bootstrap CDK (first time only)
poetry run cdk bootstrap

# Deploy all stacks
poetry run cdk deploy --all
```

See `docs/cli-playbooks/` for build, deploy, and operational runbooks.

## Stacks

| Stack | Purpose |
|---|---|
| `FargateData-lab` | Aurora Serverless v2, Secrets Manager credentials, DB security group |
| `FargateCompute-lab` | ECR, ECS cluster + service, ALB, WAF, auto scaling, KMS, SSM outputs |
| `FargateObservability-lab` | CloudWatch dashboard, alarms wired to shared SNS, log group |
| `FargateDeployment-lab` | CodeDeploy application + blue/green deployment group |
| `FargateFIS-lab` | _(disabled by default)_ Fault injection experiments — ECS task termination, CPU stress, Aurora failover |

## Application Endpoints

- `GET /` — app info
- `GET /healthz` — ALB health check target
- `GET /work?ms=250` — CPU burn for load testing
- `GET /db` — database connectivity test

## Access

```bash
# ECS Exec — no SSH, no bastion
aws ecs execute-command \
  --cluster ops-lab-fargate-cluster-lab \
  --task <task-id> \
  --container app \
  --interactive \
  --command "/bin/sh"
```

## Contrast with aws-3tier-platform

| | aws-3tier-platform (EC2) | aws-fargate-golden-path (Fargate) |
|---|---|---|
| Compute | EC2 ASG, mutable instances | Fargate tasks, immutable containers |
| Config management | Puppet via SSM | None — image is the config |
| Access | SSM Session Manager | ECS Exec |
| Deployment | Rolling AMI update | CodeDeploy blue/green |
| Scaling | ASG policies | ECS task auto scaling |
| Cost model | Always-on instances | Pay per task second |

## Project Structure

```
aws-fargate-golden-path/
├── app/                          # FastAPI application + Dockerfile
├── infra/
│   ├── app.py                    # CDK entrypoint
│   ├── cdk.json
│   ├── pyproject.toml            # Poetry dependencies
│   ├── stacks/
│   │   ├── data_stack.py         # Aurora, Secrets Manager
│   │   ├── compute_stack.py      # ECS, ECR, ALB, WAF, scaling
│   │   ├── observability_stack.py # Alarms, dashboard
│   │   ├── deployment_stack.py   # CodeDeploy blue/green
│   │   └── fis_stack.py          # Chaos experiments (disabled by default)
│   ├── custom_constructs/        # Alarms, dashboards, WAF, KMS, logging bucket
│   └── tests/
├── docs/
│   ├── cli-playbooks/
│   │   ├── 01-build-and-deploy.md
│   │   ├── 02-operations.md
│   │   └── 03-observability.md
│   └── adr/
├── ops/
│   ├── runbooks/
│   └── gamedays/
└── diagrams/
```

## Testing

```bash
cd infra && poetry run pytest tests/ -v
```

## Cost

~$50–80/month for the lab configuration (Aurora Serverless v2 min ACUs, no NAT gateway, 2 Fargate tasks at 512 CPU / 1024 MB).
