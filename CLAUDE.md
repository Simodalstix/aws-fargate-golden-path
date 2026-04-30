# CLAUDE.md — aws-fargate-golden-path

## Behavioral Guidelines

These apply to every task in this repo. They bias toward caution over speed.
For trivial tasks, use judgment.

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

For infrastructure decisions specifically:
- Name the tradeoff (Fargate vs EC2 launch type, task size, scaling trigger)
- If a CDK construct choice has implications (L1 vs L2 vs L3), surface them
- Don't silently pick CPU/memory allocation or desired count — state it and why

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked
- No abstractions for single-use constructs
- No configurability that wasn't requested
- If you write 200 lines and it could be 50, rewrite it

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:
- Don't improve adjacent code, comments, or formatting
- Don't refactor things that aren't broken
- Match existing style, even if you'd do it differently
- If you notice unrelated issues, mention them — don't fix them silently

When your changes create orphans:
- Remove imports/variables/constructs that YOUR changes made unused
- Don't remove pre-existing dead code unless asked

Every changed line should trace directly to the request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

For infrastructure tasks, replace "tests pass" with CLI or script verification:
- "Add ECS service" → verify: service stable, tasks running, ALB returns 200
- "Add scaling policy" → verify: policy attached, CloudWatch alarm wired
- "Add log group" → verify: logs appearing under /ops-lab/fargate/*

For multi-step tasks, state a brief plan first:
```
1. [Step] → verify: [CLI check]
2. [Step] → verify: [CLI check]
3. [Step] → verify: [CLI check]
```

---

## Platform Context

I am building a modular AWS ops platform as a series of independent but
interconnected GitHub projects. This repo is the container platform —
the Fargate-native alternative to the EC2 fleet in `aws-3tier-platform`.
Together they demonstrate two production fleet patterns a systems engineer
is expected to understand and operate.

**Developer:** simoda
**Machine:** SER8 (Beelink SER8, WSL Ubuntu) for dev — Minisforum UM890
  Proxmox for on-prem VMs
**Region:** ap-southeast-2
**Account:** 820242933814
**Primary tool:** Claude Code (CLI), working directly inside this repo

---

## Existing Projects

- `aws-ops-networking` ✅ — deployed. Foundation VPC. Exports to
  `/ops-lab/networking/*` in SSM Parameter Store.
- `aws-ops-observability` ✅ — deployed. Shared SNS, CloudWatch IAM policy,
  CW agent config. Exports to `/ops-lab/shared/*`.
- `aws-3tier-platform` ✅ — deployed. EC2-based fleet — ALB, ASG, RDS,
  ElastiCache. The EC2 counterpart to this repo.
- `aws-image-pipeline` 🔜 — Packer golden AMIs. Container images for this
  project live in ECR, not AMIs, but the pipeline concept is the same.
- `aws-ssm-puppet-fleet` 🔜 — SSM, Puppet, Config rules, auto-remediation.
  Manages EC2 fleets. Fargate tasks are immutable by design — no SSH,
  no config drift, no Puppet needed.
- `aws-event-driven-pipeline` 🔜 — ingests events from platform projects
  including this one.

---

## Platform Rules (apply to every project)

- **IaC:** CDK Python with Poetry — aws-cdk-lib ^2.180.0
- **No hardcoded ARNs or IDs anywhere** — all cross-project values go through
  SSM Parameter Store
- **SSM Parameter Store is the config bus** — whoever creates a resource writes
  its ID to Parameter Store; every other project reads from there at deploy time
- **NAT:** `NONE` by default — Fargate tasks in public subnets with
  `assign_public_ip=True`, no NAT cost
- **No SSH, no key pairs, no bastions** — Fargate tasks are accessed via
  ECS Exec (SSM-based), same principle as SSM Session Manager on EC2
- **Tagging:** every stack applies via `cdk.Tags.of(self).add()`:
  `Project: ops-lab`, `Stack: fargate`, `Environment: lab`
- **All projects include:**
  - CLI playbooks under `docs/cli-playbooks/`
  - Boto3 operational scripts under `scripts/`
  - This `CLAUDE.md` at repo root

---

## This Project: aws-fargate-golden-path

**Purpose:** A production-style ECS Fargate container platform — the
opinionated "golden path" pattern a platform team would hand to
application teams. Demonstrates the container-native alternative to
the EC2 ASG fleet: immutable tasks, ECR image pipeline, ECS Exec for
access, CloudWatch Container Insights for observability.

**Relationship to aws-3tier-platform:** Same application (CrossFit
FastAPI app), same foundation (networking + observability), different
compute model. EC2 ASG = mutable, Puppet-managed, AMI-based. Fargate =
immutable, container-based, no config drift possible.

### SSM Parameters This Project Reads

```
/ops-lab/networking/vpc-id
/ops-lab/networking/subnet/public-0,1,2     → Fargate tasks + ALB
/ops-lab/networking/subnet/isolated-0,1,2  → RDS (shared with 3tier or own)
/ops-lab/networking/ssm-sg-id              → baseline SG reference
/ops-lab/shared/sns-topic-arn              → alarm destination
/ops-lab/shared/cloudwatch-write-policy-arn → task execution role
```

### SSM Parameters This Project Writes

```
/ops-lab/fargate/cluster-name
/ops-lab/fargate/service-name
/ops-lab/fargate/alb-dns-name
/ops-lab/fargate/ecr-repo-uri
/ops-lab/fargate/task-definition-arn
```

### What This Stack Deploys

**ContainerStack**
- ECR repository — stores the CrossFit app container image
- ECS cluster — Fargate launch type, Container Insights enabled
- Task definition — CPU/memory sized for lab (256/512), CloudWatch log driver
- ECS service — desired count 2, circuit breaker enabled, ECS Exec enabled
- ALB — public subnets, target group pointing at Fargate tasks
- Auto scaling — target tracking on CPU and ALB request count
- CloudWatch log group — `/ops-lab/fargate/app`

**Security model**
- Task execution role — pull from ECR, write CloudWatch logs
- Task role — app permissions (Secrets Manager, SSM Parameter Store reads)
- No inbound SSH — ECS Exec is the only interactive access mechanism
- Security group — ALB → tasks on container port only, no direct public access

**Operational extensions (added incrementally)**
- CloudWatch Container Insights — task-level CPU, memory, network metrics
- CloudWatch alarms — service desired vs running count, ALB 5xx rate
- ECS deployment circuit breaker — auto-rollback on failed deployments
- Blue/green deployment via CodeDeploy (future extension)

### ECS Exec — The Fargate Equivalent of SSM Session Manager

```bash
# Drop into a running Fargate task — no SSH, no bastion
aws ecs execute-command \
  --cluster ops-lab-fargate-cluster \
  --task <task-id> \
  --container app \
  --interactive \
  --command "/bin/sh"
```

This is the access pattern to demonstrate — mirrors SSM Session Manager
on EC2. Enabled via `enable_execute_command=True` on the ECS service.

### Container Image Pipeline

```
Dockerfile in repo → docker build → ECR push → ECS service rolling deploy
```

Boto3 script handles build, tag, push, and triggers a new ECS deployment.
No CodePipeline in phase 1 — manual build/push, automated deploy trigger.

### Why No Puppet / Config Management Here

Fargate tasks are immutable by design. There is no instance to configure —
the container image is the config. If something needs to change, build a
new image and deploy. This is the key architectural contrast with the EC2
fleet in `aws-3tier-platform` and `aws-ssm-puppet-fleet`.

---

## Repo Structure

```
aws-fargate-golden-path/
├── CLAUDE.md
├── README.md
├── Dockerfile                        # CrossFit FastAPI app container
├── app.py                            # CDK entrypoint
├── cdk.json
├── pyproject.toml
├── fargate_lab/
│   ├── __init__.py
│   └── container_stack.py            # ECS, ECR, ALB, scaling, alarms
├── scripts/
│   ├── build_and_push.py             # docker build → ECR push → ECS deploy
│   ├── verify_fargate.py             # service health, task count, ALB check
│   └── exec_task.py                  # wrapper around ECS Exec
└── docs/
    └── cli-playbooks/
        ├── 01-build-and-deploy.md    # image build, ECR push, ECS rollout
        ├── 02-operations.md          # scaling, exec, log querying
        └── 03-observability.md       # Container Insights, alarms, dashboard
```

---

## Key Conventions

- Stack name: `ContainerStack`
- All SSM parameter keys: `/ops-lab/fargate/{resource}`
- All resource names: `ops-lab-fargate-{resource}`
- Tag every stack: `Project: ops-lab`, `Stack: fargate`, `Environment: lab`
- Log group pattern: `/ops-lab/fargate/{service}`
- ECS Exec always enabled — it is the only interactive access method
- Circuit breaker always enabled — auto-rollback on failed deployments
- Comments explain *why*, not just *what*
- Fargate tasks run in public subnets with public IP — no NAT cost
- Container image tag convention: `{ecr-uri}:latest` for lab,
  `{ecr-uri}:{git-sha}` for production-style deploys
