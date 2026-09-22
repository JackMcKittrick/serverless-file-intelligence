# terraform/iam.tf
# =================
# Four IAM roles for Lambda functions and Step Functions.
# All roles follow least-privilege — no wildcard actions, scoped resources where possible.
#
# IAM stays in Terraform so that cdk destroy can NEVER remove a role a running
# Lambda depends on. It also demonstrates separation of concerns: security team
# owns Terraform, app team owns CDK.
#
# WHAT TO BUILD (repeat this pattern for each role):
#
# ── ROLE 1: Lambda API execution role ─────────────────────────────────────────
#   resource "aws_iam_role" "lambda_execution" {
#     name = "${local.name_prefix}-lambda-execution-role"
#     assume_role_policy = jsonencode({...Lambda trust policy...})
#   }
#   resource "aws_iam_role_policy" "lambda_execution" {
#     role   = aws_iam_role.lambda_execution.id
#     policy = jsonencode({ permissions below })
#   }
#
#   Permissions needed:
#     DynamoDB: GetItem, PutItem, UpdateItem, DeleteItem, Query
#       on arn:aws:dynamodb:*:${account}:table/sfi-files-${env}
#          arn:aws:dynamodb:*:${account}:table/sfi-files-${env}/index/*
#     S3: GetObject, PutObject, DeleteObject, HeadObject
#       on arn:aws:s3:::sfi-uploads-${env}-${account}/*
#          arn:aws:s3:::sfi-processed-${env}-${account}/*
#     S3: GeneratePresignedUrl (use s3:PutObject with Condition:StringLike:s3:prefix)
#     SSM: GetParameter
#       on arn:aws:ssm:*:${account}:parameter/sfi/${env}/*
#     execute-api: ManageConnections   (for WebSocket pushes)
#       on arn:aws:execute-api:*:${account}:*/*/@connections/*
#     KMS: Decrypt, GenerateDataKey
#       on both KMS key ARNs
#     CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents
#       on arn:aws:logs:*:${account}:log-group:/aws/lambda/sfi-*
#     X-Ray: PutTraceSegments, PutTelemetryRecords
#
# ── ROLE 2: Processing Lambda role ────────────────────────────────────────────
#   All permissions from Role 1 PLUS:
#     Textract: DetectDocumentText, AnalyzeDocument
#     Rekognition: DetectLabels, DetectText
#     Comprehend: DetectEntities, DetectKeyPhrases
#     Bedrock: InvokeModel on model "anthropic.claude-haiku-*"
#     SNS: Publish   (for future email notifications)
#   WHY: Processing Lambdas need AI services; API Lambdas do not.
#        Least privilege means a compromised API Lambda cannot call Bedrock.
#
# ── ROLE 3: Step Functions execution role ─────────────────────────────────────
#   Trust policy: states.amazonaws.com
#   Permissions:
#     lambda: InvokeFunction
#       on arn:aws:lambda:*:${account}:function:sfi-*
#     logs: CreateLogDelivery, PutLogEvents, etc.
#       (Step Functions needs specific log delivery permissions — look these up)
#     xray: PutTraceSegments, GetSamplingRules, etc.
#
# ── ROLE 4: EventBridge Scheduler role ────────────────────────────────────────
#   Trust policy: scheduler.amazonaws.com
#   Permissions:
#     lambda: InvokeFunction
#       on ONLY arn:aws:lambda:*:${account}:function:sfi-housekeeping-${env}
#   WHY: Scope the scheduler role to the one Lambda it's allowed to invoke.
#        A compromised scheduler cannot invoke any other Lambda.
#
# ── SSM parameters for all role ARNs ─────────────────────────────────────────
#   /sfi/${env}/lambda-execution-role-arn    = aws_iam_role.lambda_execution.arn
#   /sfi/${env}/processing-lambda-role-arn   = aws_iam_role.processing_lambda.arn
#   /sfi/${env}/stepfunctions-role-arn       = aws_iam_role.step_functions.arn
#   /sfi/${env}/scheduler-role-arn           = aws_iam_role.scheduler.arn
#   WHY: CDK ApiStack and ProcessingStack read these at synth time to import the
#        roles rather than creating new ones.

# TODO: implement the four roles and their SSM parameters
