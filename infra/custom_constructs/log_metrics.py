from aws_cdk import aws_logs as logs, aws_cloudwatch as cloudwatch
from constructs import Construct


class LogMetrics(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        log_group: logs.LogGroup,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.log_group = log_group

        # Create metric filters
        self.metric_filters = []
        self._create_error_type_metric_filter()
        self._create_5xx_status_metric_filter()
        self._create_latency_metric_filter()
        self._create_request_count_metric_filter()

    def _create_error_type_metric_filter(self):
        """Create metric filter for error types from JSON logs"""
        error_type_filter = logs.MetricFilter(
            self,
            "ErrorTypeMetricFilter",
            log_group=self.log_group,
            filter_pattern=logs.FilterPattern.exists("$.errorType"),
            metric_transformations=[
                logs.MetricTransformation(
                    metric_namespace="OpsLabFargate/Application",
                    metric_name="ErrorCount",
                    metric_value="1",
                    default_value=0,
                )
            ],
        )
        self.metric_filters.append(error_type_filter)

    def _create_5xx_status_metric_filter(self):
        """Create metric filter for 5xx status codes"""
        status_5xx_filter = logs.MetricFilter(
            self,
            "Status5xxMetricFilter",
            log_group=self.log_group,
            filter_pattern=logs.FilterPattern.all(
                logs.FilterPattern.exists("$.status"),
                logs.FilterPattern.number_value("$.status", ">=", 500),
            ),
            metric_transformations=[
                logs.MetricTransformation(
                    metric_namespace="OpsLabFargate/Application",
                    metric_name="Status5xxCount",
                    metric_value="1",
                    default_value=0,
                )
            ],
        )
        self.metric_filters.append(status_5xx_filter)

    def _create_latency_metric_filter(self):
        """Create metric filter for request latency"""
        latency_filter = logs.MetricFilter(
            self,
            "LatencyMetricFilter",
            log_group=self.log_group,
            filter_pattern=logs.FilterPattern.exists("$.latencyMs"),
            metric_transformations=[
                logs.MetricTransformation(
                    metric_namespace="OpsLabFargate/Application",
                    metric_name="RequestLatency",
                    metric_value="$.latencyMs",
                    default_value=0,
                )
            ],
        )
        self.metric_filters.append(latency_filter)

    def _create_request_count_metric_filter(self):
        """Create metric filter for request count"""
        request_count_filter = logs.MetricFilter(
            self,
            "RequestCountMetricFilter",
            log_group=self.log_group,
            filter_pattern=logs.FilterPattern.exists("$.requestId"),
            metric_transformations=[
                logs.MetricTransformation(
                    metric_namespace="OpsLabFargate/Application",
                    metric_name="RequestCount",
                    metric_value="1",
                    default_value=0,
                )
            ],
        )
        self.metric_filters.append(request_count_filter)

    def get_error_count_metric(self) -> cloudwatch.Metric:
        """Get CloudWatch metric for error count"""
        return cloudwatch.Metric(
            namespace="OpsLabFargate/Application",
            metric_name="ErrorCount",
            dimensions_map={"Environment": self.env_name},
            statistic="Sum",
        )

    def get_5xx_count_metric(self) -> cloudwatch.Metric:
        """Get CloudWatch metric for 5xx status count"""
        return cloudwatch.Metric(
            namespace="OpsLabFargate/Application",
            metric_name="Status5xxCount",
            dimensions_map={"Environment": self.env_name},
            statistic="Sum",
        )

    def get_latency_metric(self) -> cloudwatch.Metric:
        """Get CloudWatch metric for request latency"""
        return cloudwatch.Metric(
            namespace="OpsLabFargate/Application",
            metric_name="RequestLatency",
            dimensions_map={"Environment": self.env_name},
            statistic="Average",
        )

    def get_request_count_metric(self) -> cloudwatch.Metric:
        """Get CloudWatch metric for request count"""
        return cloudwatch.Metric(
            namespace="OpsLabFargate/Application",
            metric_name="RequestCount",
            dimensions_map={"Environment": self.env_name},
            statistic="Sum",
        )
