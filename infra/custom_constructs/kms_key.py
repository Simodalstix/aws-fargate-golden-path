from aws_cdk import aws_kms as kms, aws_iam as iam, RemovalPolicy
from constructs import Construct


class KmsKey(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        description: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.key = kms.Key(
            self,
            "Key",
            description=description,
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,  # Set to RETAIN for production
            alias=f"ops-lab-fargate-{construct_id.lower()}-{env_name}",
        )

        # Allow CloudWatch Logs to use the key
        self.key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowCloudWatchLogs",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("logs.amazonaws.com")],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
            )
        )

        # Allow S3 to use the key
        self.key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowS3Service",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("s3.amazonaws.com")],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
            )
        )
