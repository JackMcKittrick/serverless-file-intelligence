"""
infrastructure/stacks/processing_stack.py
==========================================
CDK stack: Step Functions state machine + EventBridge rule + SQS queue.

Constructor params:
  uploads_bucket, processed_bucket, files_table  ← from StorageStack

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Read IAM role ARNs from SSM
  Processing lambda role: /sfi/{env}/processing-lambda-role-arn
  Step Functions role:     /sfi/{env}/stepfunctions-role-arn
  Import both with iam.Role.from_role_arn()

STEP 2 — Create the 3 processing Lambda functions
  Each uses make_function() pattern (same as ApiStack):
    process_document: code=backend/functions/process_document, env={UPLOADS_BUCKET}
    process_image:    code=backend/functions/process_image,    env={UPLOADS_BUCKET}
    ai_summarize:     code=backend/functions/ai_summarize,     env={BEDROCK_MODEL_ID}
  Use the processing_lambda_role (not the API lambda role — different permissions).

STEP 3 — Build the Step Functions state machine
  Import states from:
    from aws_cdk import aws_stepfunctions as sfn
    from aws_cdk import aws_stepfunctions_tasks as tasks

  States to build:
    DetermineFileType (Choice):
      - contentType starts_with "image/" → ProcessImage branch
      - default → ProcessDocument branch
    ProcessDocument (LambdaInvoke → process_document_fn)
    ProcessImage    (LambdaInvoke → process_image_fn)
    Summarize       (LambdaInvoke → ai_summarize_fn)
    ProcessingFailed (Fail state)
    Done            (Succeed state)

  Chain: DetermineFileType → (ProcessDocument | ProcessImage) → Summarize → Done
         Each LambdaInvoke: retry=[{errors: [States.TaskFailed], max_attempts: 2}]
                            catch=[{errors: [States.ALL], next: ProcessingFailed}]

  sfn.StateMachine:
    state_machine_name = f"sfi-pipeline-{environment}"
    state_machine_type = EXPRESS
    role = step_functions_role
    tracing_enabled = True
    logs = sfn.LogOptions(destination=log_group, level=ERROR)
  WHY: EXPRESS workflows are faster and cheaper for short-lived pipelines (< 5 min).
       STANDARD workflows maintain execution history for 90 days at higher cost.

STEP 4 — Create the SQS queue (buffer between EventBridge and Step Functions)
  sqs.Queue:
    queue_name = f"sfi-processing-{environment}"
    visibility_timeout = Duration.seconds(300)
    dead_letter_queue = sqs.DeadLetterQueue(max_receive_count=3, queue=dlq)
  Also create a DLQ (dead-letter queue) with 14-day retention.
  WHY: SQS decouples S3 events from Step Functions. If Step Functions is throttled
       or the state machine fails to start, messages wait in the queue (not lost).
       DLQ captures messages that fail 3 times for manual investigation.

STEP 5 — EventBridge rule: S3 ObjectCreated → SQS
  events.Rule:
    event_pattern = {source: ["aws.s3"],
                     detail_type: ["Object Created"],
                     detail: {bucket: {name: [uploads_bucket.bucket_name]}}}
    targets = [SqsQueue(processing_queue)]
  WHY: EventBridge routes S3 upload events to SQS without polling. The uploads
       bucket has enable_event_bridge_notification() called in StorageStack (Step 4).

STEP 6 — SQS → Step Functions trigger (Lambda bridge)
  Create a small Lambda that reads from the SQS queue and starts a Step Functions
  execution per message:
    sfn_client.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps({"fileId": ..., "userId": ..., "s3Key": ..., "contentType": ...})
    )
  Add SQS event source to this Lambda.
  WHY: CDK's built-in SqsToStepFunctions L3 construct is limited; a small bridge
       Lambda gives you full control over the input shape.

STEP 7 — CfnOutputs + Python properties
  Output: StateMachineArn
  Property: state_machine (for MonitoringStack)
"""

from aws_cdk import Stack, Duration, CfnOutput
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class ProcessingStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 environment: str,
                 uploads_bucket: s3.IBucket,
                 processed_bucket: s3.IBucket,
                 files_table: dynamodb.Table,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # TODO: implement Steps 1-7 described above

    @property
    def state_machine(self) -> sfn.StateMachine:
        raise NotImplementedError("Implement Step 3 first")
