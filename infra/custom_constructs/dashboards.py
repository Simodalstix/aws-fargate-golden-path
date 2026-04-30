from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs as ecs,
    aws_rds as rds,
    aws_wafv2 as wafv2,
    Duration,
    Stack,
)
from constructs import Construct


class Dashboards(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        alb: elbv2.ApplicationLoadBalancer,
        ecs_service: ecs.FargateService,
        database,
        waf_web_acl,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.alb = alb
        self.ecs_service = ecs_service
        self.database = database
        self.waf_web_acl = waf_web_acl

        # Create main dashboard
        self.dashboard = cloudwatch.Dashboard(
            self,
            "MainDashboard",
            dashboard_name=f"ops-lab-fargate-{env_name}",
            period_override=cloudwatch.PeriodOverride.AUTO,
            start="-PT6H",  # Last 6 hours
        )

        # Add widgets to dashboard
        self.dashboard.add_widgets(*self._create_alb_widgets())
        self.dashboard.add_widgets(*self._create_ecs_widgets())
        self.dashboard.add_widgets(*self._create_rds_widgets())
        self.dashboard.add_widgets(*self._create_waf_widgets())

    def _create_alb_widgets(self):
        """Create ALB monitoring widgets"""
        # ALB Request Count
        request_count_widget = cloudwatch.GraphWidget(
            title="ALB Request Count",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="RequestCount",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
        )

        # ALB Response Times
        response_time_widget = cloudwatch.GraphWidget(
            title="ALB Response Times",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="TargetResponseTime",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Average",
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="TargetResponseTime",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="p95",
                    period=Duration.minutes(5),
                    label="p95",
                ),
            ],
            width=6,
            height=6,
        )

        # ALB HTTP Status Codes
        http_codes_widget = cloudwatch.GraphWidget(
            title="ALB HTTP Status Codes",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="HTTPCode_Target_2XX_Count",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="2XX",
                    color=cloudwatch.Color.GREEN,
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="HTTPCode_Target_4XX_Count",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="4XX",
                    color=cloudwatch.Color.ORANGE,
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="HTTPCode_Target_5XX_Count",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="5XX",
                    color=cloudwatch.Color.RED,
                ),
            ],
            width=6,
            height=6,
        )

        # ALB Target Health
        target_health_widget = cloudwatch.GraphWidget(
            title="ALB Target Health",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="HealthyHostCount",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Healthy Targets",
                    color=cloudwatch.Color.GREEN,
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="UnHealthyHostCount",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Unhealthy Targets",
                    color=cloudwatch.Color.RED,
                ),
            ],
            width=6,
            height=6,
        )

        return [
            request_count_widget,
            response_time_widget,
            http_codes_widget,
            target_health_widget,
        ]

    def _create_ecs_widgets(self):
        """Create ECS monitoring widgets"""
        # ECS CPU Utilization
        cpu_widget = cloudwatch.GraphWidget(
            title="ECS CPU Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "ServiceName": self.ecs_service.service_name,
                        "ClusterName": self.ecs_service.cluster.cluster_name,
                    },
                    statistic="Average",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
            left_y_axis=cloudwatch.YAxisProps(min=0, max=100),
        )

        # ECS Memory Utilization
        memory_widget = cloudwatch.GraphWidget(
            title="ECS Memory Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "ServiceName": self.ecs_service.service_name,
                        "ClusterName": self.ecs_service.cluster.cluster_name,
                    },
                    statistic="Average",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
            left_y_axis=cloudwatch.YAxisProps(min=0, max=100),
        )

        # ECS Task Count
        task_count_widget = cloudwatch.GraphWidget(
            title="ECS Running Task Count",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="RunningTaskCount",
                    dimensions_map={
                        "ServiceName": self.ecs_service.service_name,
                        "ClusterName": self.ecs_service.cluster.cluster_name,
                    },
                    statistic="Average",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
        )

        # Request Count Per Target
        request_per_target_widget = cloudwatch.GraphWidget(
            title="Request Count Per Target",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="RequestCountPerTarget",
                    dimensions_map={"LoadBalancer": self.alb.load_balancer_full_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
        )

        return [cpu_widget, memory_widget, task_count_widget, request_per_target_widget]

    def _create_rds_widgets(self):
        """Create RDS monitoring widgets"""
        # Get database identifier
        if hasattr(self.database, "cluster_identifier"):
            db_identifier = self.database.cluster_identifier
            namespace = "AWS/RDS"
            dimension_name = "DBClusterIdentifier"
        else:
            db_identifier = self.database.instance_identifier
            namespace = "AWS/RDS"
            dimension_name = "DBInstanceIdentifier"

        # RDS CPU Utilization
        rds_cpu_widget = cloudwatch.GraphWidget(
            title="RDS CPU Utilization",
            left=[
                cloudwatch.Metric(
                    namespace=namespace,
                    metric_name="CPUUtilization",
                    dimensions_map={dimension_name: db_identifier},
                    statistic="Average",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
            left_y_axis=cloudwatch.YAxisProps(min=0, max=100),
        )

        # RDS Database Connections
        rds_connections_widget = cloudwatch.GraphWidget(
            title="RDS Database Connections",
            left=[
                cloudwatch.Metric(
                    namespace=namespace,
                    metric_name="DatabaseConnections",
                    dimensions_map={dimension_name: db_identifier},
                    statistic="Average",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
        )

        # RDS Free Storage Space
        rds_storage_widget = cloudwatch.GraphWidget(
            title="RDS Free Storage Space",
            left=[
                cloudwatch.Metric(
                    namespace=namespace,
                    metric_name="FreeStorageSpace",
                    dimensions_map={dimension_name: db_identifier},
                    statistic="Average",
                    period=Duration.minutes(5),
                )
            ],
            width=6,
            height=6,
        )

        # RDS Read/Write Latency
        rds_latency_widget = cloudwatch.GraphWidget(
            title="RDS Read/Write Latency",
            left=[
                cloudwatch.Metric(
                    namespace=namespace,
                    metric_name="ReadLatency",
                    dimensions_map={dimension_name: db_identifier},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Read Latency",
                ),
                cloudwatch.Metric(
                    namespace=namespace,
                    metric_name="WriteLatency",
                    dimensions_map={dimension_name: db_identifier},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Write Latency",
                ),
            ],
            width=6,
            height=6,
        )

        return [
            rds_cpu_widget,
            rds_connections_widget,
            rds_storage_widget,
            rds_latency_widget,
        ]

    def _create_waf_widgets(self):
        """Create WAF monitoring widgets"""
        # WAF Allowed vs Blocked Requests
        waf_requests_widget = cloudwatch.GraphWidget(
            title="WAF Allowed vs Blocked Requests",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/WAFV2",
                    metric_name="AllowedRequests",
                    dimensions_map={
                        "WebACL": self.waf_web_acl.web_acl.name,
                        "Region": Stack.of(self).region,
                        "Rule": "ALL",
                    },
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Allowed",
                    color=cloudwatch.Color.GREEN,
                ),
                cloudwatch.Metric(
                    namespace="AWS/WAFV2",
                    metric_name="BlockedRequests",
                    dimensions_map={
                        "WebACL": self.waf_web_acl.web_acl.name,
                        "Region": Stack.of(self).region,
                        "Rule": "ALL",
                    },
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Blocked",
                    color=cloudwatch.Color.RED,
                ),
            ],
            width=12,
            height=6,
        )

        return [waf_requests_widget]
