from aws_cdk import (
    Stack,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_sns as sns,
    aws_ssm as ssm,
    CfnOutput,
    Tags,
)
from constructs import Construct
from custom_constructs.dashboards import Dashboards
from custom_constructs.alarms import Alarms


class ObservabilityStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        alb: elbv2.ApplicationLoadBalancer,
        ecs_service: ecs.FargateService,
        database,
        waf_web_acl,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # Import the shared SNS topic from aws-ops-observability
        sns_topic_arn = ssm.StringParameter.value_for_string_parameter(
            self, "/ops-lab/shared/sns-topic-arn"
        )
        alarm_topic = sns.Topic.from_topic_arn(self, "SharedAlarmTopic", sns_topic_arn)

        self.log_group = logs.LogGroup.from_log_group_name(
            self,
            "ApplicationLogGroup",
            log_group_name="/ops-lab/fargate/app",
        )

        self.dashboards = Dashboards(
            self,
            "Dashboards",
            env_name=env_name,
            alb=alb,
            ecs_service=ecs_service,
            database=database,
            waf_web_acl=waf_web_acl,
        )

        self.alarms = Alarms(
            self,
            "Alarms",
            env_name=env_name,
            alb=alb,
            ecs_service=ecs_service,
            database=database,
            waf_web_acl=waf_web_acl,
            alarm_topic=alarm_topic,
        )

        # Expose critical alarms for FIS stop conditions
        self.critical_alarms = [
            alarm for alarm in self.alarms.alarms
            if "5xx" in alarm.alarm_name
            or "unhealthy-targets" in alarm.alarm_name
            or "task-count" in alarm.alarm_name
        ]

        Tags.of(self).add("Project", "ops-lab")
        Tags.of(self).add("Stack", "fargate")
        Tags.of(self).add("Environment", env_name)

        CfnOutput(
            self, "DashboardURL",
            value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name={self.dashboards.dashboard.dashboard_name}",
            description="CloudWatch Dashboard URL",
            export_name=f"FargateObservability-{env_name}-DashboardURL",
        )
        CfnOutput(
            self, "LogGroupName",
            value=self.log_group.log_group_name,
            description="Application log group name",
            export_name=f"FargateObservability-{env_name}-LogGroupName",
        )
        CfnOutput(
            self, "ErrorLogsQuery",
            value="fields @timestamp, requestId, path, status, errorType, latencyMs | filter ispresent(errorType) | sort @timestamp desc | limit 100",
            description="CloudWatch Insights query for error logs",
        )
        CfnOutput(
            self, "SlowRequestsQuery",
            value="fields @timestamp, requestId, path, status, latencyMs | filter latencyMs > 1000 | sort latencyMs desc | limit 100",
            description="CloudWatch Insights query for slow requests",
        )
        CfnOutput(
            self, "Status5xxQuery",
            value="fields @timestamp, requestId, path, status, errorType, latencyMs | filter status >= 500 | sort @timestamp desc | limit 100",
            description="CloudWatch Insights query for 5xx status codes",
        )
        CfnOutput(
            self, "RequestsByPathQuery",
            value="stats count() by path | sort count desc",
            description="CloudWatch Insights query for requests by path",
        )
