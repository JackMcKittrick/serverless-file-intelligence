"""
infrastructure/stacks/monitoring_stack.py
==========================================
CDK stack: CloudWatch dashboard + alarms + SNS alerts. Deploy last.

Constructor params:
  api_stack        ← from ApiStack
  processing_stack ← from ProcessingStack

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Create an SNS topic for alarm notifications
  sns.Topic(topic_name=f"sfi-alerts-{environment}")
  Subscribe the ALERT_EMAIL env var using sns.EmailSubscription.
  WHY: CloudWatch alarms publish to SNS; SNS emails the on-call address.
       Email subscription requires manual confirmation after first deploy.

STEP 2 — Create CloudWatch alarms
  For each alarm, use cloudwatch.Alarm with:
    alarm_name, metric, threshold, comparison_operator, evaluation_periods
    alarm_actions = [cw_actions.SnsAction(alert_topic)]

  Alarms to build:
    a. API 5xx errors:
       metric = api_stack.rest_api.metric_server_error()
       threshold = 10 (errors in 5 minutes)
    b. Step Functions execution failures:
       metric = processing_stack.state_machine.metric_failed()
       threshold = 1 (any failure)
    c. SQS DLQ messages:
       metric = dlq.metric_approximate_number_of_messages_visible()
       threshold = 1
  WHY: These three alarms cover the most critical failure modes:
       the API layer, the processing pipeline, and the queue safety net.

STEP 3 — Create a CloudWatch Dashboard
  cloudwatch.Dashboard(dashboard_name=f"sfi-{environment}")
  Add widgets:
    TextWidget: "# SFI Dashboard — {environment}"
    GraphWidget: API 5xx rate
    GraphWidget: Step Functions executions started/succeeded/failed
    SingleValueWidget: DLQ message count
    GraphWidget: Lambda duration (P50/P95) for key functions
  WHY: A dashboard gives you a single-pane view of system health at a glance,
       without needing to know which individual metrics to look up.

STEP 4 — CfnOutput
  Output: DashboardUrl (link to the CloudWatch console dashboard)
"""

from aws_cdk import Stack, CfnOutput
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
import os
from constructs import Construct


class MonitoringStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 environment: str,
                 api_stack,
                 processing_stack,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # TODO: implement Steps 1-4 described above
