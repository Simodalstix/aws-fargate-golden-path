from aws_cdk import (
    Stack,
    aws_codedeploy as codedeploy,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs as ecs,
    aws_iam as iam,
    CfnOutput,
    Duration,
    Tags,
)
from constructs import Construct


class DeploymentStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        ecs_service: ecs.FargateService,
        alb: elbv2.ApplicationLoadBalancer,
        target_group_1: elbv2.ApplicationTargetGroup,
        target_group_2: elbv2.ApplicationTargetGroup,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        self.codedeploy_service_role = iam.Role(
            self,
            "CodeDeployServiceRole",
            assumed_by=iam.ServicePrincipal("codedeploy.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSCodeDeployRoleForECS"
                )
            ],
        )

        self.codedeploy_application = codedeploy.EcsApplication(
            self,
            "CodeDeployApplication",
            application_name=f"ops-lab-fargate-app-{env_name}",
        )

        self.deployment_group = codedeploy.EcsDeploymentGroup(
            self,
            "DeploymentGroup",
            application=self.codedeploy_application,
            deployment_group_name=f"ops-lab-fargate-dg-{env_name}",
            service=ecs_service,
            blue_green_deployment_config=codedeploy.EcsBlueGreenDeploymentConfig(
                blue_target_group=target_group_1,
                green_target_group=target_group_2,
                listener=alb.listeners[0],
                deployment_approval_wait_time=Duration.minutes(0),
                termination_wait_time=Duration.minutes(5),
            ),
            deployment_config=codedeploy.EcsDeploymentConfig.CANARY_10_PERCENT_5_MINUTES,
            role=self.codedeploy_service_role,
            auto_rollback=codedeploy.AutoRollbackConfig(
                failed_deployment=True,
                stopped_deployment=True,
                deployment_in_alarm=False,
            ),
        )

        Tags.of(self).add("Project", "ops-lab")
        Tags.of(self).add("Stack", "fargate")
        Tags.of(self).add("Environment", env_name)

        CfnOutput(
            self, "CodeDeployApplicationName",
            value=self.codedeploy_application.application_name,
            description="CodeDeploy application name",
            export_name=f"FargateDeployment-{env_name}-CodeDeployApplicationName",
        )
        CfnOutput(
            self, "CodeDeployDeploymentGroupName",
            value=self.deployment_group.deployment_group_name,
            description="CodeDeploy deployment group name",
            export_name=f"FargateDeployment-{env_name}-CodeDeployDeploymentGroupName",
        )
