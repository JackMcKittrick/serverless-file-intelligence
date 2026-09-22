# terraform/outputs.tf
# =====================
# Terraform outputs — printed after every apply, and readable via
# `terraform output -json` for scripting / CI verification.
#
# NOTE: These are TERRAFORM outputs (printed to terminal), not SSM parameters
#       (which CDK reads at synth time). The SSM parameters are created in
#       kms.tf, iam.tf, s3.tf, and waf.tf next to the resources they describe.
#       Outputs here are for human operators, not for CDK.
#
# WHAT TO BUILD:
#
# ── OUTPUT 1: uploads_bucket_name ────────────────────────────────────────────
#   output "uploads_bucket_name" {
#     description = "Name of the S3 bucket for raw file uploads"
#     value       = aws_s3_bucket.uploads.id
#   }
#
# ── OUTPUT 2: processed_bucket_name ──────────────────────────────────────────
#   output "processed_bucket_name" {
#     description = "Name of the S3 bucket for processed results"
#     value       = aws_s3_bucket.processed.id
#   }
#
# ── OUTPUT 3: uploads_kms_key_arn ────────────────────────────────────────────
#   output "uploads_kms_key_arn" {
#     description = "ARN of the KMS key used for S3 encryption"
#     value       = aws_kms_key.uploads.arn
#   }
#
# ── OUTPUT 4: table_kms_key_arn ──────────────────────────────────────────────
#   output "table_kms_key_arn" {
#     description = "ARN of the KMS key used for DynamoDB encryption"
#     value       = aws_kms_key.table.arn
#   }
#
# ── OUTPUT 5: lambda_execution_role_arn ──────────────────────────────────────
#   output "lambda_execution_role_arn" {
#     description = "ARN of the IAM role for API Lambda functions"
#     value       = aws_iam_role.lambda_execution.arn
#   }
#
# ── OUTPUT 6: processing_lambda_role_arn ─────────────────────────────────────
#   output "processing_lambda_role_arn" {
#     description = "ARN of the IAM role for Processing Lambda functions"
#     value       = aws_iam_role.processing_lambda.arn
#   }
#
# ── OUTPUT 7: step_functions_role_arn ────────────────────────────────────────
#   output "step_functions_role_arn" {
#     description = "ARN of the IAM role for Step Functions execution"
#     value       = aws_iam_role.step_functions.arn
#   }
#
# ── OUTPUT 8: scheduler_role_arn ─────────────────────────────────────────────
#   output "scheduler_role_arn" {
#     description = "ARN of the IAM role for EventBridge Scheduler"
#     value       = aws_iam_role.scheduler.arn
#   }
#
# ── OUTPUT 9: waf_web_acl_arn ────────────────────────────────────────────────
#   output "waf_web_acl_arn" {
#     description = "ARN of the WAF WebACL attached to CloudFront"
#     value       = aws_wafv2_web_acl.main.arn
#   }
#
# ── OUTPUT 10: ssm_parameter_paths ───────────────────────────────────────────
#   output "ssm_parameter_paths" {
#     description = "Map of SSM parameter paths that CDK reads at synth time"
#     value = {
#       uploads_bucket_name       = "/sfi/${local.env}/uploads-bucket-name"
#       processed_bucket_name     = "/sfi/${local.env}/processed-bucket-name"
#       uploads_bucket_arn        = "/sfi/${local.env}/uploads-bucket-arn"
#       uploads_kms_key_arn       = "/sfi/${local.env}/uploads-kms-key-arn"
#       table_kms_key_arn         = "/sfi/${local.env}/table-kms-key-arn"
#       lambda_execution_role_arn = "/sfi/${local.env}/lambda-execution-role-arn"
#       processing_lambda_role_arn = "/sfi/${local.env}/processing-lambda-role-arn"
#       stepfunctions_role_arn    = "/sfi/${local.env}/stepfunctions-role-arn"
#       scheduler_role_arn        = "/sfi/${local.env}/scheduler-role-arn"
#       waf_web_acl_arn           = "/sfi/${local.env}/waf-web-acl-arn"
#     }
#   }
#   WHY: Run `terraform output -json ssm_parameter_paths` after apply to confirm
#        all paths CDK expects are populated before running `cdk synth`.

# TODO: implement the 10 outputs described above
