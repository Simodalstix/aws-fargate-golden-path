from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs as ecs,
    Duration,
    Stack,
)
from constructs import Construct


class Alarms(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        alb: elbv2.ApplicationLoadBalancer,
        ecs_service: ecs.FargateService,
        database,
        waf_web_acl,
        alarm_topic: sns.ITopic,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.alb = alb
        self.ecs_service = ecs_service
        self.database = database
        self.waf_web_acl = waf_web_acl
        self.alarm_topic = alarm_topic

        self.alarms = []
        self._create_alb_alarms()
        self._create_ecs_alarms()
        self._create_rds_alarms()
        self._create_waf_alarms()

    def _create_alb_alarms(self):
        alb_5xx_alarm = cloudwatch.Alarm(
            self,
            "ALB5xxAlarm",
            alarm_name=f"ops-lab-fargate-alb-5xx-{self.env_name}",
            alarm_description="ALB 5xx error rate is too high",
            metric=cloudwatch.MathExpression(
                expression="(m1/m2)*100",
                using_metrics={
                    "m1": cloudwatch.Metric(
                        namespace="AWS/ApplicationELB",
                        metric_name="HTTPCode_Target_5XX_Count",
                        dimensions_map={
                            "LoadBalancer": self.alb.load_balancer_full_name
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    ),
                    "m2": cloudwatch.Metric(
                        namespace="AWS/ApplicationELB",
                        metric_name="RequestCount",
                        dimensions_map={
                            "LoadBalancer": self.alb.load_balancer_full_name
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    ),
                },
                label="5xx Error Rate (%)",
            ),
            threshold=1.0,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alb_5xx_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(alb_5xx_alarm)

        alb_response_time_alarm = cloudwatch.Alarm(
            self,
            "ALBResponseTimeAlarm",
            alarm_name=f"ops-lab-fargate-alb-response-time-{self.env_name}",
            alarm_description="ALB response time p95 is too high",
            metric=cloudwatch.Metric(
                namespace="AWS/ApplicationELB",
                metric_name="TargetResponseTime",
                dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                statistic="p95",
                period=Duration.minutes(5),
            ),
            threshold=2.0,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alb_response_time_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(alb_response_time_alarm)

        alb_unhealthy_targets_alarm = cloudwatch.Alarm(
            self,
            "ALBUnhealthyTargetsAlarm",
            alarm_name=f"ops-lab-fargate-alb-unhealthy-targets-{self.env_name}",
            alarm_description="ALB has unhealthy targets",
            metric=cloudwatch.Metric(
                namespace="AWS/ApplicationELB",
                metric_name="UnHealthyHostCount",
                dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=0,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alb_unhealthy_targets_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )
        self.alarms.append(alb_unhealthy_targets_alarm)

    def _create_ecs_alarms(self):
        ecs_task_count_alarm = cloudwatch.Alarm(
            self,
            "ECSTaskCountAlarm",
            alarm_name=f"ops-lab-fargate-ecs-task-count-{self.env_name}",
            alarm_description="ECS running task count is below desired",
            metric=cloudwatch.Metric(
                namespace="AWS/ECS",
                metric_name="RunningTaskCount",
                dimensions_map={
                    "ServiceName": self.ecs_service.service_name,
                    "ClusterName": self.ecs_service.cluster.cluster_name,
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
        )
        ecs_task_count_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(ecs_task_count_alarm)

        ecs_cpu_alarm = cloudwatch.Alarm(
            self,
            "ECSCPUAlarm",
            alarm_name=f"ops-lab-fargate-ecs-cpu-{self.env_name}",
            alarm_description="ECS CPU utilization is too high",
            metric=cloudwatch.Metric(
                namespace="AWS/ECS",
                metric_name="CPUUtilization",
                dimensions_map={
                    "ServiceName": self.ecs_service.service_name,
                    "ClusterName": self.ecs_service.cluster.cluster_name,
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        ecs_cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(ecs_cpu_alarm)

        ecs_memory_alarm = cloudwatch.Alarm(
            self,
            "ECSMemoryAlarm",
            alarm_name=f"ops-lab-fargate-ecs-memory-{self.env_name}",
            alarm_description="ECS memory utilization is too high",
            metric=cloudwatch.Metric(
                namespace="AWS/ECS",
                metric_name="MemoryUtilization",
                dimensions_map={
                    "ServiceName": self.ecs_service.service_name,
                    "ClusterName": self.ecs_service.cluster.cluster_name,
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        ecs_memory_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(ecs_memory_alarm)

    def _create_rds_alarms(self):
        if hasattr(self.database, "cluster_identifier"):
            db_identifier = self.database.cluster_identifier
            namespace = "AWS/RDS"
            dimension_name = "DBClusterIdentifier"
        else:
            db_identifier = self.database.instance_identifier
            namespace = "AWS/RDS"
            dimension_name = "DBInstanceIdentifier"

        rds_cpu_alarm = cloudwatch.Alarm(
            self,
            "RDSCPUAlarm",
            alarm_name=f"ops-lab-fargate-rds-cpu-{self.env_name}",
            alarm_description="RDS CPU utilization is too high",
            metric=cloudwatch.Metric(
                namespace=namespace,
                metric_name="CPUUtilization",
                dimensions_map={dimension_name: db_identifier},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        rds_cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(rds_cpu_alarm)

        rds_connections_alarm = cloudwatch.Alarm(
            self,
            "RDSConnectionsAlarm",
            alarm_name=f"ops-lab-fargate-rds-connections-{self.env_name}",
            alarm_description="RDS database connections are too high",
            metric=cloudwatch.Metric(
                namespace=namespace,
                metric_name="DatabaseConnections",
                dimensions_map={dimension_name: db_identifier},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        rds_connections_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(rds_connections_alarm)

        rds_storage_alarm = cloudwatch.Alarm(
            self,
            "RDSStorageAlarm",
            alarm_name=f"ops-lab-fargate-rds-storage-{self.env_name}",
            alarm_description="RDS free storage space is low",
            metric=cloudwatch.Metric(
                namespace=namespace,
                metric_name="FreeStorageSpace",
                dimensions_map={dimension_name: db_identifier},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=2000000000,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        rds_storage_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(rds_storage_alarm)

    def _create_waf_alarms(self):
        waf_blocked_alarm = cloudwatch.Alarm(
            self,
            "WAFBlockedAlarm",
            alarm_name=f"ops-lab-fargate-waf-blocked-{self.env_name}",
            alarm_description="WAF blocked requests surge detected",
            metric=cloudwatch.Metric(
                namespace="AWS/WAFV2",
                metric_name="BlockedRequests",
                dimensions_map={
                    "WebACL": self.waf_web_acl.web_acl.name,
                    "Region": Stack.of(self).region,
                    "Rule": "ALL",
                },
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=100,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        waf_blocked_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(waf_blocked_alarm)

        waf_rate_limit_alarm = cloudwatch.Alarm(
            self,
            "WAFRateLimitAlarm",
            alarm_name=f"ops-lab-fargate-waf-rate-limit-{self.env_name}",
            alarm_description="WAF rate limit rule triggered",
            metric=cloudwatch.Metric(
                namespace="AWS/WAFV2",
                metric_name="BlockedRequests",
                dimensions_map={
                    "WebACL": self.waf_web_acl.web_acl.name,
                    "Region": Stack.of(self).region,
                    "Rule": "RateLimitRule",
                },
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=10,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        waf_rate_limit_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
        self.alarms.append(waf_rate_limit_alarm)
