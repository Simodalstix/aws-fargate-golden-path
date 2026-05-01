from aws_cdk import aws_s3 as s3, aws_iam as iam, RemovalPolicy, Duration
from constructs import Construct
import hashlib


class LoggingBucket(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ALB access logs require SSE-S3 — KMS is not supported by the ALB log delivery service
        self.bucket = s3.Bucket(
            self,
            "Bucket",
            bucket_name=f"ops-lab-fargate-alb-logs-{env_name}-{hashlib.md5(self.node.addr.encode()).hexdigest()[:8]}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ALBLogsLifecycle",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.DEEP_ARCHIVE,
                            transition_after=Duration.days(365),
                        ),
                    ],
                    expiration=Duration.days(2555),
                )
            ],
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="ALBLogDelivery",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("elasticloadbalancing.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{self.bucket.bucket_arn}/AWSLogs/*"],
            )
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="ALBLogDeliveryWrite",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("elasticloadbalancing.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{self.bucket.bucket_arn}/*"],
                conditions={
                    "StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control"}
                },
            )
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="ALBLogDeliveryAclCheck",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("elasticloadbalancing.amazonaws.com")],
                actions=["s3:GetBucketAcl"],
                resources=[self.bucket.bucket_arn],
            )
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="DenyInsecureConnections",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[self.bucket.bucket_arn, f"{self.bucket.bucket_arn}/*"],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )
