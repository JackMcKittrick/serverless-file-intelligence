import os

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct


class MonitoringStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        api_stack,
        processing_stack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment
        period = Duration.minutes(5) # defines a 5 minute metric period thatll be used by alarms and dashborads
        dlq = processing_stack.dlq  # store that dead letter queue from other stack as a local variable

        # an email address where alerts will be sent
        alert_email = os.environ.get("ALERT_EMAIL", "").strip()
        if not alert_email:
            raise ValueError("ALERT_EMAIL environment variable must be set")

        # creates an SNS topic
        alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name=f"sfi-alerts-{environment}",
        )
        # creates an email subscription and then attaches it to the SNS topic just created
        alert_topic.add_subscription(
            subscriptions.EmailSubscription(alert_email)
        )
        
        # below are cloudwatch metrics from other stacks thatll be used to create alarms
        # metric_server_error means http 5xx errors
        # rest_api is an object for api gateway rest api
        api_errors = api_stack.rest_api.metric_server_error(
            period=period, # this will group metric data into 5 minute chunks
            statistic="Sum", # add up all the values occuring during the period
            # here its api errors so 1 API error + 1 API error + etc
        )
        # metric_failed() is how many executions of this step functions workflow failed
        execution_failures = processing_stack.state_machine.metric_failed(
            period=period,
            statistic="Sum",
        )
        # ApproximateNumberOfMessagesVisible means how many messages are currently sitting i the queue waiting to be read
        dlq_depth = dlq.metric_approximate_number_of_messages_visible(
            period=period,
            statistic="Maximum",
        )
        # start a loop with 3 tuples of 5 values thatll be used to create one alarm per tuple
        for construct_name, alarm_name, metric, threshold in [
            (
                # CDK identifier, AWS alarm name, metric, and threshold
                "ApiServerErrorsAlarm",
                f"sfi-api-5xx-{environment}",
                api_errors,
                10,
            ),
            (
                "ExecutionFailuresAlarm",
                f"sfi-execution-failures-{environment}",
                execution_failures,
                5,
            ),
            (
                "DlqMessagesAlarm",
                f"sfi-dlq-messages-{environment}",
                dlq_depth,
                0,
            ),
        ]:
            # create the cloudwatch alarm
            alarm = cloudwatch.Alarm(
                # apply the values in the tuples
                self,
                construct_name,
                alarm_name=alarm_name,
                metric=metric,
                threshold=threshold,
                comparison_operator=(
                    # makes the comparison strictly greater than the threshold
                    cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
                ),
                evaluation_periods=1,  # evaluates once per metric period so 5 minutes
                datapoints_to_alarm=1,   # requiers one breaching datapoint out of that one evaluated period
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                # missing metric data alone doesn't trigger the alarm
            )
            # creates an action that publishes a message to this sns topic
            # then attaches this action to the alarm 
            alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # creates an empty list thatll hold calculated error rate metric for each lambda func
        lambda_error_rates = []
        seen_functions = set()  # set so dont use same function twice

        # walks thru constructs contained in each of the two stacks
        for source_stack in (api_stack, processing_stack):
            for construct in source_stack.node.find_all():
                # skips over non lambda functions
                if not isinstance(construct, lambda_.Function):
                    continue
                # skips if already processed
                if construct.node.addr in seen_functions:
                    continue
                # records lambda functino as processed 
                # every CDK construct has a code containing metadata
                # so construct.node.addr is a unique ID that CDK assigns to the contruct
                seen_functions.add(construct.node.addr)
                # gets length of error rates this is used to create unique metric IDs
                i = len(lambda_error_rates)
                # adds following calcuated metric to the list 
                lambda_error_rates.append(
                    # creates a CW metric math expression
                    cloudwatch.MathExpression(
                        # error percentage
                        expression=f"IF(inv{i} > 0, 100 * err{i} / inv{i}, 0)",
                        using_metrics={ # errors is functions totla errors during each 5 min period
                            # a metric ID is like a variable name in code 
                            # errors = LambdaA errors for example
                            # if I have two different lambdas then ill also have
                            # errors = LambdaB errors so theres two things called errors its not unique
                            # the for loop is whats creating the duplicates
                            # not a problem in python bc local vairable changes lambda functions its later when CDK builds one cloudwatch graph
                            f"err{i}": construct.metric_errors(period=period, statistic="Sum"),
                            # invocations is times lambda ran in the period
                            f"inv{i}": construct.metric_invocations(period=period, statistic="Sum"),
                        },
                        period=period,
                        label=f"{construct.node.id} errors (%)",
                    )
                ) # this isnt an alarm its a new metric derived from other metrics

        # creates a cloud watch dashboard
        dashboard = cloudwatch.Dashboard(
            self,
            "Dashboard",
            dashboard_name=f"sfi-{environment}",
        )
        # a widget is a visual box on the dashboard
        dashboard.add_widgets(
            # creates a heading 
            cloudwatch.TextWidget(
                # makes it a header
                markdown=f"# SFI Dashboard — {environment}",
                width=24, # span dashboard grid width
                height=1,  # makes heading one grid unit tall 
            )
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Request Count",
                left=[  # starts list of metrics plotted on the graphs left vertical axis
                    api_stack.rest_api.metric_count(
                        period=period,
                        statistic="Sum",
                    )
                ],
                width=12, # graph is half the dashboard width 
            ),
            cloudwatch.GraphWidget(
                title="API Latency",
                left=[ # plots median API latency so half requests above or below this value
                    api_stack.rest_api.metric_latency(
                        period=period,
                        statistic="p50",
                        label="P50",
                    ),   # plots 95th percentile API latency to expose slower requests
                    api_stack.rest_api.metric_latency(
                        period=period,
                        statistic="p95",
                        label="P95",
                    ),
                ],
                width=12,
            ),
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget( # plots successful executations in 5 min period
                # successful executions means entire step functions workflow finished 
                title="Step Functions Executions",
                left=[
                    processing_stack.state_machine.metric_succeeded(
                        period=period,
                        statistic="Sum",
                        label="Succeeded",
                    ),
                    execution_failures,
                ],
                width=12,  # half the board
            ),
            cloudwatch.GraphWidget(  # use error percentage metric created above
                title="Lambda Error Rates (%)",
                left=lambda_error_rates,
                width=12,  # half board
            ),
        )
        dashboard.add_widgets(  # displays the dlq metric as a number across full width
            cloudwatch.SingleValueWidget(
                title="DLQ Depth",
                metrics=[dlq_depth],
                width=24,
            )
        )

        CfnOutput(
            self,
            "DashboardUrl",
            value=(
                f"https://{self.region}.{self.url_suffix}/cloudwatch/home"
                f"?region={self.region}#dashboards:name={dashboard.dashboard_name}"
            ),
        )
