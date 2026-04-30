#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.data_stack import DataStack
from stacks.compute_stack import ComputeStack
from stacks.observability_stack import ObservabilityStack
from stacks.deployment_stack import DeploymentStack
from stacks.fis_stack import FISStack

app = cdk.App()

env_name = app.node.try_get_context("envName") or "lab"
db_engine = app.node.try_get_context("dbEngine") or "aurora-postgres"
rotate_secrets = app.node.try_get_context("rotateSecrets") or False
min_acu = app.node.try_get_context("minAcu") or 0.5
max_acu = app.node.try_get_context("maxAcu") or 1
desired_count = app.node.try_get_context("desiredCount") or 2
cpu = app.node.try_get_context("cpu") or 512
memory_mib = app.node.try_get_context("memoryMiB") or 1024
enable_fis = app.node.try_get_context("enableFIS") or False

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

data_stack = DataStack(
    app,
    f"FargateData-{env_name}",
    env_name=env_name,
    db_engine=db_engine,
    rotate_secrets=rotate_secrets,
    min_acu=min_acu,
    max_acu=max_acu,
    env=env,
)

compute_stack = ComputeStack(
    app,
    f"FargateCompute-{env_name}",
    database=data_stack.database,
    db_secret=data_stack.db_secret,
    env_name=env_name,
    desired_count=desired_count,
    cpu=cpu,
    memory_mib=memory_mib,
    env=env,
)

observability_stack = ObservabilityStack(
    app,
    f"FargateObservability-{env_name}",
    alb=compute_stack.alb,
    ecs_service=compute_stack.ecs_service,
    database=data_stack.database,
    waf_web_acl=compute_stack.waf_web_acl,
    env_name=env_name,
    env=env,
)

deployment_stack = DeploymentStack(
    app,
    f"FargateDeployment-{env_name}",
    ecs_service=compute_stack.ecs_service,
    alb=compute_stack.alb,
    target_group_1=compute_stack.target_group_1,
    target_group_2=compute_stack.target_group_2,
    env_name=env_name,
    env=env,
)

if enable_fis:
    fis_stack = FISStack(
        app,
        f"FargateFIS-{env_name}",
        vpc=compute_stack.vpc,
        ecs_cluster=compute_stack.ecs_cluster,
        ecs_service=compute_stack.ecs_service,
        database=data_stack.database,
        stop_condition_alarms=observability_stack.critical_alarms,
        env_name=env_name,
        env=env,
    )
    fis_stack.add_dependency(observability_stack)

compute_stack.add_dependency(data_stack)
observability_stack.add_dependency(compute_stack)
deployment_stack.add_dependency(compute_stack)

app.synth()
