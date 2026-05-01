from aws_cdk import (
    Stack,
    Duration,
    Tags,
    aws_fis as fis,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct
from typing import List


class FISStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        vpc: ec2.Vpc,
        ecs_cluster: ecs.Cluster,
        ecs_service: ecs.FargateService,
        database,
        stop_condition_alarms: List[cloudwatch.Alarm],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.vpc = vpc
        self.ecs_cluster = ecs_cluster
        self.ecs_service = ecs_service
        self.database = database
        self.stop_condition_alarms = stop_condition_alarms

        self.fis_role = self._create_fis_role()

        self.experiments = {}
        self._create_ecs_experiments()
        self._create_database_experiments()

        Tags.of(self).add("Project", "ops-lab")
        Tags.of(self).add("Stack", "fargate")
        Tags.of(self).add("Environment", env_name)

    def _create_fis_role(self) -> iam.Role:
        role = iam.Role(
            self,
            "FISRole",
            role_name=f"ops-lab-fargate-fis-role-{self.env_name}",
            assumed_by=iam.ServicePrincipal("fis.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchReadOnlyAccess")
            ],
        )

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecs:StopTask",
                    "ecs:ListTasks",
                    "ecs:DescribeTasks",
                    "ecs:DescribeServices",
                    "ecs:DescribeClusters",
                ],
                resources=["*"],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds:FailoverDBCluster",
                    "rds:DescribeDBClusters",
                    "rds:DescribeDBInstances",
                ],
                resources=["*"],
            )
        )

        # aws:ecs:task-cpu-stress requires SSM to run its action agent inside the task
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:SendCommand",
                    "ssm:ListCommands",
                    "ssm:GetCommandInvocation",
                ],
                resources=["*"],
            )
        )

        return role

    def _create_ecs_experiments(self):
        self.experiments["ecs_task_termination"] = fis.CfnExperimentTemplate(
            self,
            "ECSTaskTermination",
            description="Stop 50% of Fargate tasks to verify ECS auto-recovery and ALB failover",
            role_arn=self.fis_role.role_arn,
            actions={
                "StopTasks": {
                    "actionId": "aws:ecs:stop-task",
                    "parameters": {
                        "clusterArn": self.ecs_cluster.cluster_arn,
                        "serviceName": self.ecs_service.service_name,
                    },
                    "targets": {"Tasks": "ECSTasksTarget"},
                }
            },
            targets={
                "ECSTasksTarget": {
                    "resourceType": "aws:ecs:task",
                    "resourceArns": ["*"],
                    "selectionMode": "PERCENT(50)",
                    "resourceTags": {"Environment": self.env_name},
                }
            },
            stop_conditions=[
                {"source": "aws:cloudwatch:alarm", "value": alarm.alarm_arn}
                for alarm in self.stop_condition_alarms
            ],
            tags={
                "Name": f"ops-lab-fargate-ecs-task-termination-{self.env_name}",
                "Environment": self.env_name,
                "ExperimentType": "ECS",
            },
        )

        self.experiments["ecs_cpu_stress"] = fis.CfnExperimentTemplate(
            self,
            "ECSCPUStress",
            description="Inject 80% CPU stress into one Fargate task to trigger autoscaling",
            role_arn=self.fis_role.role_arn,
            actions={
                "CPUStress": {
                    "actionId": "aws:ecs:task-cpu-stress",
                    "parameters": {
                        "duration": "PT10M",
                        "percent": "80",
                    },
                    "targets": {"Tasks": "ECSTasksTarget"},
                }
            },
            targets={
                "ECSTasksTarget": {
                    "resourceType": "aws:ecs:task",
                    "resourceArns": ["*"],
                    "selectionMode": "COUNT(1)",
                    "resourceTags": {"Environment": self.env_name},
                }
            },
            stop_conditions=[
                {"source": "aws:cloudwatch:alarm", "value": alarm.alarm_arn}
                for alarm in self.stop_condition_alarms
            ],
            tags={
                "Name": f"ops-lab-fargate-ecs-cpu-stress-{self.env_name}",
                "Environment": self.env_name,
                "ExperimentType": "ECS",
            },
        )

    def _create_database_experiments(self):
        if not hasattr(self.database, "cluster_identifier"):
            return

        self.experiments["aurora_failover"] = fis.CfnExperimentTemplate(
            self,
            "AuroraFailover",
            description="Force Aurora failover to test URL shortener resilience during DB writer transition",
            role_arn=self.fis_role.role_arn,
            actions={
                "FailoverCluster": {
                    "actionId": "aws:rds:failover-db-cluster",
                    "parameters": {"forceFailover": "true"},
                    "targets": {"Clusters": "AuroraClusterTarget"},
                }
            },
            targets={
                "AuroraClusterTarget": {
                    "resourceType": "aws:rds:cluster",
                    "resourceArns": [
                        f"arn:aws:rds:{Stack.of(self).region}:{Stack.of(self).account}"
                        f":cluster:{self.database.cluster_identifier}"
                    ],
                    "selectionMode": "ALL",
                }
            },
            stop_conditions=[
                {"source": "aws:cloudwatch:alarm", "value": alarm.alarm_arn}
                for alarm in self.stop_condition_alarms
            ],
            tags={
                "Name": f"ops-lab-fargate-aurora-failover-{self.env_name}",
                "Environment": self.env_name,
                "ExperimentType": "Database",
            },
        )
