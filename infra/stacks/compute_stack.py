from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    aws_wafv2 as wafv2,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Tags,
)
from constructs import Construct
from custom_constructs.kms_key import KmsKey
from custom_constructs.logging_bucket import LoggingBucket
from custom_constructs.waf_web_acl import WafWebAcl


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        database,
        db_secret: secretsmanager.Secret,
        env_name: str,
        desired_count: int = 2,
        cpu: int = 512,
        memory_mib: int = 1024,
        enable_break_fix: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.database = database
        self.db_secret = db_secret

        # Look up the shared VPC from aws-ops-networking
        vpc_id = ssm.StringParameter.value_from_lookup(
            self, "/ops-lab/networking/vpc-id"
        )
        self.vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id)

        self.kms_key = KmsKey(
            self,
            "ComputeKmsKey",
            env_name=env_name,
            description=f"KMS key for Fargate compute resources in {env_name}",
        )

        self.logging_bucket = LoggingBucket(
            self, "ALBLoggingBucket", env_name=env_name, kms_key=self.kms_key.key
        )

        self.waf_web_acl = WafWebAcl(self, "WAFWebACL", env_name=env_name)

        self.ecr_repository = ecr.Repository(
            self,
            "ECRRepository",
            repository_name=f"ops-lab-fargate-app-{env_name}",
            removal_policy=RemovalPolicy.DESTROY,
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(description="Keep last 10 images", max_image_count=10)
            ],
        )

        self.ecs_cluster = ecs.Cluster(
            self,
            "ECSCluster",
            cluster_name=f"ops-lab-fargate-cluster-{env_name}",
            vpc=self.vpc,
            enable_fargate_capacity_providers=True,
            container_insights=True,
        )

        self.log_group = logs.LogGroup(
            self,
            "ApplicationLogGroup",
            log_group_name="/ops-lab/fargate/app",
            retention=logs.RetentionDays.ONE_MONTH,
            encryption_key=self.kms_key.key,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self._create_security_groups()
        self._create_application_load_balancer()
        self._create_ecs_service(cpu, memory_mib, desired_count, enable_break_fix)

        # Associate WAF with ALB
        wafv2.CfnWebACLAssociation(
            self,
            "WAFAssociation",
            resource_arn=self.alb.load_balancer_arn,
            web_acl_arn=self.waf_web_acl.web_acl_arn,
        )

        # Allow DB connections from ECS tasks
        database.connections.allow_from(
            self.ecs_security_group,
            ec2.Port.tcp(5432),
            "ECS tasks to Aurora",
        )

        Tags.of(self).add("Project", "ops-lab")
        Tags.of(self).add("Stack", "fargate")
        Tags.of(self).add("Environment", env_name)

        # Write outputs to SSM for downstream consumers
        ssm.StringParameter(
            self, "ClusterNameParam",
            parameter_name="/ops-lab/fargate/cluster-name",
            string_value=self.ecs_cluster.cluster_name,
        )
        ssm.StringParameter(
            self, "ServiceNameParam",
            parameter_name="/ops-lab/fargate/service-name",
            string_value=self.ecs_service.service_name,
        )
        ssm.StringParameter(
            self, "AlbDnsNameParam",
            parameter_name="/ops-lab/fargate/alb-dns-name",
            string_value=self.alb.load_balancer_dns_name,
        )
        ssm.StringParameter(
            self, "EcrRepoUriParam",
            parameter_name="/ops-lab/fargate/ecr-repo-uri",
            string_value=self.ecr_repository.repository_uri,
        )
        ssm.StringParameter(
            self, "TaskDefinitionArnParam",
            parameter_name="/ops-lab/fargate/task-definition-arn",
            string_value=self.task_definition.task_definition_arn,
        )

        CfnOutput(
            self, "ALBDNSName",
            value=self.alb.load_balancer_dns_name,
            description="ALB DNS name",
            export_name=f"FargateCompute-{env_name}-ALBDNSName",
        )
        CfnOutput(
            self, "ECRRepositoryURI",
            value=self.ecr_repository.repository_uri,
            description="ECR repository URI",
            export_name=f"FargateCompute-{env_name}-ECRRepositoryURI",
        )
        CfnOutput(
            self, "ECSClusterName",
            value=self.ecs_cluster.cluster_name,
            description="ECS cluster name",
            export_name=f"FargateCompute-{env_name}-ECSClusterName",
        )
        CfnOutput(
            self, "ECSServiceName",
            value=self.ecs_service.service_name,
            description="ECS service name",
            export_name=f"FargateCompute-{env_name}-ECSServiceName",
        )

    def _create_security_groups(self):
        self.alb_security_group = ec2.SecurityGroup(
            self,
            "ALBSecurityGroup",
            vpc=self.vpc,
            description="Security group for ALB",
            security_group_name=f"ops-lab-fargate-alb-sg-{self.env_name}",
            allow_all_outbound=False,
        )
        self.alb_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP inbound",
        )
        self.alb_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS inbound",
        )

        self.ecs_security_group = ec2.SecurityGroup(
            self,
            "ECSSecurityGroup",
            vpc=self.vpc,
            description="Security group for ECS tasks",
            security_group_name=f"ops-lab-fargate-ecs-sg-{self.env_name}",
            allow_all_outbound=True,
        )
        self.ecs_security_group.add_ingress_rule(
            peer=self.alb_security_group,
            connection=ec2.Port.tcp(80),
            description="Allow inbound from ALB",
        )
        self.alb_security_group.add_egress_rule(
            peer=self.ecs_security_group,
            connection=ec2.Port.tcp(80),
            description="Allow outbound to ECS",
        )

    def _create_application_load_balancer(self):
        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "ALB",
            vpc=self.vpc,
            internet_facing=True,
            load_balancer_name=f"ops-lab-fargate-alb-{self.env_name}",
            security_group=self.alb_security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            deletion_protection=self.env_name != "dev",
        )
        self.alb.log_access_logs(
            bucket=self.logging_bucket.bucket, prefix=f"alb-logs/{self.env_name}"
        )

        # Two target groups required for CodeDeploy blue/green
        self.target_group_1 = elbv2.ApplicationTargetGroup(
            self, "TargetGroup1",
            vpc=self.vpc,
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            target_group_name=f"ops-lab-fargate-tg1-{self.env_name}",
            health_check=elbv2.HealthCheck(
                enabled=True,
                healthy_http_codes="200",
                path="/healthz",
                protocol=elbv2.Protocol.HTTP,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )
        self.target_group_2 = elbv2.ApplicationTargetGroup(
            self, "TargetGroup2",
            vpc=self.vpc,
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            target_group_name=f"ops-lab-fargate-tg2-{self.env_name}",
            health_check=elbv2.HealthCheck(
                enabled=True,
                healthy_http_codes="200",
                path="/healthz",
                protocol=elbv2.Protocol.HTTP,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )

        self.listener = self.alb.add_listener(
            "Listener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.forward([self.target_group_1]),
        )

    def _create_ecs_service(
        self, cpu: int, memory_mib: int, desired_count: int, enable_break_fix: bool
    ):
        self.task_execution_role = iam.Role(
            self,
            "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        self.ecr_repository.grant_pull(self.task_execution_role)
        self.log_group.grant_write(self.task_execution_role)
        self.db_secret.grant_read(self.task_execution_role)

        self.task_role = iam.Role(
            self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        self.db_secret.grant_read(self.task_role)

        if enable_break_fix:
            self.task_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["ssm:GetParameter"],
                    resources=[
                        f"arn:aws:ssm:{self.region}:{self.account}:parameter/ops-lab/fargate/failure-mode"
                    ],
                )
            )

        self.task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )

        self.task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            family=f"ops-lab-fargate-task-{self.env_name}",
            cpu=cpu,
            memory_limit_mib=memory_mib,
            execution_role=self.task_execution_role,
            task_role=self.task_role,
        )

        self.app_container = self.task_definition.add_container(
            "AppContainer",
            image=ecs.ContainerImage.from_asset("../app"),
            container_name="app",
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="app", log_group=self.log_group
            ),
            environment={
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "PARAM_FAILURE_MODE": (
                    "/ops-lab/fargate/failure-mode" if enable_break_fix else ""
                ),
                "AWS_REGION": self.region,
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost/healthz || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )
        self.app_container.add_port_mappings(
            ecs.PortMapping(container_port=80, protocol=ecs.Protocol.TCP)
        )

        self.xray_container = self.task_definition.add_container(
            "XRayContainer",
            image=ecs.ContainerImage.from_registry(
                "public.ecr.aws/xray/aws-xray-daemon:latest"
            ),
            container_name="xray-daemon",
            cpu=32,
            memory_limit_mib=256,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="xray", log_group=self.log_group
            ),
            user="1337",
        )
        self.xray_container.add_port_mappings(
            ecs.PortMapping(container_port=2000, protocol=ecs.Protocol.UDP)
        )

        self.ecs_service = ecs.FargateService(
            self,
            "ECSService",
            cluster=self.ecs_cluster,
            task_definition=self.task_definition,
            service_name=f"ops-lab-fargate-service-{self.env_name}",
            desired_count=desired_count,
            # Public subnets + public IP — no NAT cost
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            assign_public_ip=True,
            security_groups=[self.ecs_security_group],
            enable_execute_command=True,
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(capacity_provider="FARGATE", weight=1)
            ],
            health_check_grace_period=Duration.seconds(60),
            min_healthy_percent=100,
            max_healthy_percent=200,
            # CODE_DEPLOY controller is required for the DeploymentStack blue/green setup
            deployment_controller=ecs.DeploymentController(
                type=ecs.DeploymentControllerType.CODE_DEPLOY
            ),
        )
        self.ecs_service.attach_to_application_target_group(self.target_group_1)

        self.scaling_target = self.ecs_service.auto_scale_task_count(
            min_capacity=desired_count, max_capacity=desired_count * 4
        )
        self.scaling_target.scale_on_cpu_utilization(
            "CPUScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2),
        )
        self.scaling_target.scale_on_request_count(
            "RequestCountScaling",
            requests_per_target=1000,
            target_group=self.target_group_1,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2),
        )
