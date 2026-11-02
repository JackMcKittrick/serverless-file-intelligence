import textwrap
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct


class ProcessingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        uploads_bucket: s3.IBucket,  # IBucket is an interface either a bucket created elsewhere in app or imported
        processed_bucket: s3.IBucket,
        files_table: dynamodb.Table,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # imports and creates CDK refrenece for processing lambda role made in terraform
        processing_lambda_role = iam.Role.from_role_arn(
            self,
            "ProcessingLambdaRole",
            ssm.StringParameter.value_for_string_parameter(
                self,
                f"/sfi/{environment}/processing-lambda-role-arn",
            ),
            mutable=False,
        )
        # CDK reference for step function role
        step_functions_role = iam.Role.from_role_arn(
            self,
            "StepFunctionsRole",
            ssm.StringParameter.value_for_string_parameter(
                self,
                f"/sfi/{environment}/stepfunctions-role-arn",
            ),
            mutable=False,  # CDK cant add permissions to this imported role
        )

        # moves up three directory levels to get absolute resolved path
        project_root = Path(__file__).resolve().parents[2]
        # sees if user provided a config valud named bedrock_model_id and gives default if not
        bedrock_model_id = (
            self.node.try_get_context("bedrock_model_id")
            or "amazon.nova-micro-v1:0"
        )

        # this was used in API stack as well so farmiliar
        def make_function(
            construct_name: str,
            function_name: str,
            function_environment: dict,
        ) -> lambda_.Function:
            return lambda_.Function(
                self,
                construct_name,
                function_name=f"sfi-{function_name.replace('_', '-')}-{environment}",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="handler.handler",
                code=lambda_.Code.from_asset(
                    str(project_root / "backend" / "functions" / function_name)
                ),
                role=processing_lambda_role,
                timeout=Duration.seconds(60),
                memory_size=512,
                environment=function_environment,
            )

        # done API stack so farmiliar makes lambda functions from file and handler
        process_document_fn = make_function(
            "ProcessDocumentFunction",
            "process_document",
            {"UPLOADS_BUCKET": uploads_bucket.bucket_name},  # supplies some enviroment variables
        )

        process_image_fn = make_function(
            "ProcessImageFunction",
            "process_image",
            {"UPLOADS_BUCKET": uploads_bucket.bucket_name},
        )

        ai_summarize_fn = make_function(
            "AiSummarizeFunction",
            "ai_summarize",
            {"BEDROCK_MODEL_ID": bedrock_model_id},
        )

        # creates a step frunction failure state thatll immediately end workflow and record an error and failure reason
        processing_failed = sfn.Fail(
            self,
            "ProcessingFailed",
            error="ProcessingFailed",
            cause="A processing Lambda failed.",
        )
        # a successful terminal state 
        # so workflow ends on ProcessingFailed or Done
        done = sfn.Succeed(self, "Done")

        # same purpose as make_function helper
        # it creates a step function state that invokes a lambda
        def make_task(
            state_name: str,  # name shown in workflow
            function: lambda_.IFunction,
        ) -> tasks.LambdaInvoke:
            # specifies what lambda gets invoked
            task = tasks.LambdaInvoke(
                self,
                state_name,
                lambda_function=function,
                payload_response_only=True,
                 # dont have a result_path so a successful task will replace input with lambdas returned payload
                retry_on_service_exceptions=False,
                # disables constructs automatic lambda service error retry policy
            )
            # use this specific retry policy
            task.add_retry(
                errors=["States.TaskFailed"], # covers these failures
                interval=Duration.seconds(2),  # wait before retry
                backoff_rate=2, # doubles rate for next retry
                max_attempts=2, # two retries
            )
            task.add_catch( # adds an error handler
                processing_failed, # sends caught failure to ProcessingFailed state
                errors=["States.ALL"],  
                result_path="$.error",  # places erorr in info under error field
            )
            return task

        # uses the helper above to make the step function worklow tasks
        process_document = make_task(
            "ProcessDocument",
            process_document_fn,
        )
        process_image = make_task(
            "ProcessImage",
            process_image_fn,
        )
        summarize = make_task(
            "Summarize",
            ai_summarize_fn,
        )

        # connects the succesful doc processing to summarization
        process_document.next(summarize)
        # connects successful image processing to summarization
        process_image.next(summarize)
        summarize.next(done)  # connects successful summarization to done state

        # creates a condiition that requires all of its conditions to be true
        # step functions carry around a json object while it runs
        # JSON is the workflows input
        # so $ means start at the root of the current JSON data
        # is this document a PDF or text file
        document_condition = sfn.Condition.and_(
            sfn.Condition.is_present("$.contentType"),
            sfn.Condition.is_string("$.contentType"),
            sfn.Condition.or_(
                sfn.Condition.string_matches("$.contentType", "*pdf*"),
                sfn.Condition.string_matches("$.contentType", "*text*"),
            ),
        )

        # creates a branching state named determine_file_type
        # a branching statement is like an if/else statement inside a step function
        determine_file_type = sfn.Choice(self, "DetermineFileType")
        # routes PDF or text documents to document processing
        determine_file_type.when(document_condition, process_document)
        # routes everything else to image processing
        determine_file_type.otherwise(process_image)

        # define a cloudwatch logs log group
        # a container that holds logs for a resource containing one or many streams
        log_group = logs.LogGroup(
            self,
            "ProcessingStateMachineLogs",
            retention=logs.RetentionDays.ONE_MONTH,  # retains logs for 30 days
        )

        # creates the workflow resource and stores it on the stack
        self._state_machine = sfn.StateMachine(
            self,
            "ProcessingStateMachine",
            state_machine_name=f"sfi-pipeline-{environment}",
            state_machine_type=sfn.StateMachineType.EXPRESS,
            # express workflow is a type of step function optimized for high volume short running workflows
            definition_body=sfn.DefinitionBody.from_chainable(
                determine_file_type
            ),  # builds workflow from starting choice state to all connected
            role=step_functions_role,  # assigns role
            timeout=Duration.minutes(5),
            tracing_enabled=True,  
            logs=sfn.LogOptions( # send logs to previously created log group
                destination=log_group,
                level=sfn.LogLevel.ERROR,
                include_execution_data=True,  
                # includes input and output data in log entries
            ),
        )

        # create a dead letter queue like a failed messages parking lot
        # instead of losing the message forever aws saves it here so later can be inspected
        dlq = sqs.Queue(
            self,
            "ProcessingDeadLetterQueue",
            queue_name=f"sfi-processing-dlq-{environment}",
            retention_period=Duration.days(14),  # keep for 14 days
            encryption=sqs.QueueEncryption.SQS_MANAGED,  
            # server side encryptino using SQS managed keys so aws encrypts before writing to storage
            enforce_ssl=True,
        )
        # create the main queue
        self._queue = sqs.Queue(
            self,
            "ProcessingQueue",
            queue_name=f"sfi-processing-{environment}",
            visibility_timeout=Duration.seconds(300),  
            # hide for 300 secs after consumer receives a message
            # becomes avaliable again if failed or not deleted
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, # 3 tries before move to dlq
                queue=dlq,
            ),  # configs where repeatedly failing messages go
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
        )

        # defines an eventbridge rule
        # event bridge is the start of the upload processing pipeline 
        # sends event to SQS then bridge lambda defined below starts step function
        # remember live browser updates are done thru dynamoDB streams and websockets
        # logging and alerts done by cloudwatch
        # eventbridge scheduler triggers the housekeeping at a set time
        events.Rule(
            self,
            "UploadsObjectCreatedRule",
            rule_name=f"sfi-uploads-object-created-{environment}",
            event_pattern=events.EventPattern( # define which events match
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": { # matching events just to uploads bucket
                        "name": [uploads_bucket.bucket_name],
                    },
                },
            ), # where matching events are sent
            targets=[targets.SqsQueue(self._queue)],
        )

        # this code creates lambda function with the job of reading SQS messages and starting step functions execution
        bridge = lambda_.Function(
            self,
            "ProcessingQueueBridge",
            function_name=f"sfi-processing-bridge-{environment}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",   # this is written inline below
            # CDK packages supplied code into index.py
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "STATE_MACHINE_ARN": self._state_machine.state_machine_arn, # stores state machine arn in env variable
                "UPLOADS_BUCKET": uploads_bucket.bucket_name,
            },  # tells CDK that lambdas soruce code is supplied directly as a string
            code=lambda_.Code.from_inline(
                textwrap.dedent(  # removes shared leading indentation from string
                    """ 
                    import json
                    import logging
                    import os

                    import boto3

                    logger = logging.getLogger()   # creates a logger object its a tool to write log messages
                    logger.setLevel(logging.INFO)   # minimum severity level actually recorded

                    s3 = boto3.client("s3")
                    step_functions = boto3.client("stepfunctions")

                    # event is the SQS message batch
                    def handler(event, context):
                        failures = []  # empty list of IDs of messages not handled successfully
                        # loops over every message in the batch
                        # record holds one SQS message at a time
                        for record in event.get("Records", []):
                            try:
                                # necessary parsing similar to code written prior
                                message = json.loads(record["body"])
                                detail = message["detail"]
                                bucket = detail["bucket"]["name"]
                                key = detail["object"]["key"]
                                
                                if bucket != os.environ["UPLOADS_BUCKET"]:
                                    raise ValueError("Unexpected upload bucket")
                                
                                # creates a dictionary of args for a s3 head_object() request
                                # its an API call that gets info about object but not actual file
                                head_args = {
                                    "Bucket": bucket,
                                    "Key": key,  # will sepcify what object 
                                }
                                # adds version id if it exists
                                version_id = detail["object"].get("version-id")
                                if version_id:
                                    head_args["VersionId"] = version_id

                                # calls s3 to retrieve the objects headers and metadata
                                head = s3.head_object(**head_args)
                                # extracts metadata
                                metadata = head.get("Metadata", {})

                                # look for file identifier and user
                                # file identifier is generated randomly by app
                                # and userID is assigned by cognito at account creation
                                file_id = metadata.get("fileid") or metadata.get("file-id")
                                user_id = metadata.get("userid") or metadata.get("user-id")

                                if not file_id or not user_id:
                                    raise ValueError(
                                        "Upload metadata must include fileid and userid"
                                    )

                                # dictionary taht will be step functions execution intput
                                payload = {
                                    "fileId": file_id,
                                    "userId": user_id,
                                    "s3Key": key,
                                    "contentType": head.get(
                                        "ContentType",
                                        "application/octet-stream",
                                    ).lower(),
                                }
                                # calls step function API to start new execution
                                step_functions.start_execution(
                                    stateMachineArn=os.environ["STATE_MACHINE_ARN"],
                                    input=json.dumps(payload),
                                )

                            except Exception:
                                logger.exception(
                                    "Failed to start processing for message %s",
                                    record["messageId"],
                                )
                                failures.append(
                                    {"itemIdentifier": record["messageId"]}
                                )

                        return {"batchItemFailures": failures}
                    """
                ).strip()
            ),
        )

        uploads_bucket.grant_read(bridge) # lets bridge lambda read objects from uploads bucket
        self._state_machine.grant_start_execution(bridge)  # lets bridge start execution of state machine

        # configs bridge lambda to be invoked and pool sqs queue
        bridge.add_event_source(
            event_sources.SqsEventSource(
                self._queue,
                batch_size=10,
                report_batch_item_failures=True,
            )
        )

        CfnOutput(
            self,
            "StateMachineArn",
            value=self._state_machine.state_machine_arn,
        )

        CfnOutput(
            self,
            "ProcessingQueueUrl",
            value=self._queue.queue_url,
        )

    @property
    def state_machine(self) -> sfn.StateMachine:
        return self._state_machine

    @property
    def queue(self) -> sqs.Queue:
        return self._queue