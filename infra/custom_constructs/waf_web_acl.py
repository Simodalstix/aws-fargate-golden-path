from aws_cdk import aws_wafv2 as wafv2, aws_cloudwatch as cloudwatch, CfnOutput, Stack
from constructs import Construct


class WafWebAcl(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, env_name: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create WAF Web ACL
        self.web_acl = wafv2.CfnWebACL(
            self,
            "WebACL",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            name=f"ops-lab-fargate-waf-{env_name}",
            description=f"WAF Web ACL for ops-lab Fargate {env_name}",
            rules=[
                # AWS Managed Rules - Common Rule Set
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=1,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        count={}  # Start in COUNT mode for tuning
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS", name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name="CommonRuleSetMetric",
                    ),
                ),
                # AWS Managed Rules - Known Bad Inputs
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesKnownBadInputsRuleSet",
                    priority=2,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        count={}  # Start in COUNT mode for tuning
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesKnownBadInputsRuleSet",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name="KnownBadInputsMetric",
                    ),
                ),
                # AWS Managed Rules - Amazon IP Reputation List
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesAmazonIpReputationList",
                    priority=3,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        count={}  # Start in COUNT mode for tuning
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesAmazonIpReputationList",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name="IpReputationMetric",
                    ),
                ),
                # Rate-based rule
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimitRule",
                    priority=4,
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        count={}  # Start in COUNT mode for tuning
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=2000,  # 2000 requests per 5 minutes
                            aggregate_key_type="IP",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimitMetric",
                    ),
                ),
            ],
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name=f"OpsLabFargateWAF{env_name}",
            ),
        )

        # Create CloudWatch dashboard widget for WAF metrics
        self.waf_widget = cloudwatch.GraphWidget(
            title="WAF Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/WAFV2",
                    metric_name="AllowedRequests",
                    dimensions_map={
                        "WebACL": self.web_acl.name,
                        "Region": Stack.of(self).region,
                        "Rule": "ALL",
                    },
                    statistic="Sum",
                ),
                cloudwatch.Metric(
                    namespace="AWS/WAFV2",
                    metric_name="BlockedRequests",
                    dimensions_map={
                        "WebACL": self.web_acl.name,
                        "Region": Stack.of(self).region,
                        "Rule": "ALL",
                    },
                    statistic="Sum",
                ),
            ],
            width=12,
            height=6,
        )

    @property
    def web_acl_arn(self) -> str:
        return self.web_acl.attr_arn

    @property
    def web_acl_id(self) -> str:
        return self.web_acl.attr_id
