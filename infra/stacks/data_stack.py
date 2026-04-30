from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Tags,
)
from constructs import Construct


class DataStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        db_engine: str = "aurora-postgres",
        rotate_secrets: bool = False,
        min_acu: float = 0.5,
        max_acu: float = 1,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # Look up the shared VPC from aws-ops-networking
        vpc_id = ssm.StringParameter.value_from_lookup(
            self, "/ops-lab/networking/vpc-id"
        )
        self.vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id)

        self.db_subnet_group = rds.SubnetGroup(
            self,
            "DBSubnetGroup",
            description=f"Subnet group for {env_name} fargate database",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            subnet_group_name=f"ops-lab-fargate-db-subnet-group-{env_name}",
        )

        self.db_security_group = ec2.SecurityGroup(
            self,
            "DatabaseSecurityGroup",
            vpc=self.vpc,
            description="Security group for Fargate RDS database",
            security_group_name=f"ops-lab-fargate-db-sg-{env_name}",
            allow_all_outbound=False,
        )

        self.db_secret = secretsmanager.Secret(
            self,
            "DatabaseSecret",
            description=f"Fargate database credentials for {env_name}",
            secret_name=f"ops-lab/fargate/db-credentials/{env_name}",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "dbadmin"}',
                generate_string_key="password",
                exclude_characters=" %+~`#$&*()|[]{}:;<>?!'/\"\\",
                password_length=32,
            ),
        )

        if db_engine == "aurora-postgres":
            self._create_aurora_postgres_cluster(min_acu, max_acu)
        elif db_engine == "postgres":
            self._create_postgres_instance()
        elif db_engine == "mysql":
            self._create_mysql_instance()
        else:
            raise ValueError(f"Unsupported database engine: {db_engine}")

        if rotate_secrets:
            self._setup_secret_rotation()

        # SSM parameter for break/fix lab failure mode
        self.failure_mode_parameter = ssm.StringParameter(
            self,
            "FailureModeParameter",
            parameter_name="/ops-lab/fargate/failure-mode",
            string_value="none",
            description="Controls application failure modes for break/fix lab",
            tier=ssm.ParameterTier.STANDARD,
        )

        Tags.of(self.database).add("Project", "ops-lab")
        Tags.of(self.database).add("Stack", "fargate")
        Tags.of(self.database).add("Environment", env_name)

        CfnOutput(
            self,
            "DatabaseEndpoint",
            value=(
                self.database.cluster_endpoint.hostname
                if hasattr(self.database, "cluster_endpoint")
                else self.database.instance_endpoint.hostname
            ),
            description="Database endpoint",
            export_name=f"FargateData-{env_name}-DatabaseEndpoint",
        )

        CfnOutput(
            self,
            "DatabaseSecretArn",
            value=self.db_secret.secret_arn,
            description="Database secret ARN",
            export_name=f"FargateData-{env_name}-DatabaseSecretArn",
        )

        CfnOutput(
            self,
            "DatabaseSecurityGroupId",
            value=self.db_security_group.security_group_id,
            description="Database security group ID",
            export_name=f"FargateData-{env_name}-DatabaseSecurityGroupId",
        )

    def _create_aurora_postgres_cluster(self, min_acu: float, max_acu: float):
        self.database = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_3
            ),
            credentials=rds.Credentials.from_secret(self.db_secret),
            writer=rds.ClusterInstance.serverless_v2("writer"),
            readers=[
                rds.ClusterInstance.serverless_v2("reader", scale_with_writer=True)
            ],
            serverless_v2_min_capacity=min_acu,
            serverless_v2_max_capacity=max_acu,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[self.db_security_group],
            subnet_group=self.db_subnet_group,
            default_database_name="opslab",
            backup=rds.BackupProps(
                retention=Duration.days(30),
                preferred_window="03:00-04:00",
            ),
            deletion_protection=self.env_name != "dev",
            removal_policy=RemovalPolicy.DESTROY,
            cluster_identifier=f"ops-lab-fargate-aurora-{self.env_name}",
            cloudwatch_logs_exports=["postgresql"],
        )

    def _create_postgres_instance(self):
        self.database = rds.DatabaseInstance(
            self,
            "PostgreSQLInstance",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15_3
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            credentials=rds.Credentials.from_secret(self.db_secret),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[self.db_security_group],
            subnet_group=self.db_subnet_group,
            default_database_name="opslab",
            backup_retention=Duration.days(7),
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            instance_identifier=f"ops-lab-fargate-postgres-{self.env_name}",
            monitoring_interval=Duration.seconds(60),
            enable_performance_insights=True,
            performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            cloudwatch_logs_exports=["postgresql"],
        )

    def _create_mysql_instance(self):
        self.database = rds.DatabaseInstance(
            self,
            "MySQLInstance",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0_35
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            credentials=rds.Credentials.from_secret(self.db_secret),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[self.db_security_group],
            subnet_group=self.db_subnet_group,
            default_database_name="opslab",
            backup_retention=Duration.days(7),
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            instance_identifier=f"ops-lab-fargate-mysql-{self.env_name}",
            monitoring_interval=Duration.seconds(60),
            enable_performance_insights=True,
            performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            cloudwatch_logs_exports=["error", "general", "slow-query"],
        )

    def _setup_secret_rotation(self):
        if hasattr(self.database, "add_rotation_single_user"):
            self.database.add_rotation_single_user()
        else:
            self.db_secret.add_rotation_schedule(
                "RotationSchedule",
                automatically_after=Duration.days(30),
            )
