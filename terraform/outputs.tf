# terraform/outputs.tf
# =====================
# Terraform outputs — printed after every apply

output "uploads_bucket_name" {
  description = "Name of the S3 bucket for raw file uploads"
  value       = aws_s3_bucket.uploads.id
}

# terraform outputs do not create anything, they just expose a value it already knows
# when you do terraform output these are the values which are shown
# its common that people output name, arn, etc

output "processed_bucket_name" {
  description = "Name of the S3 bucket for processed results"
  value       = aws_s3_bucket.processed.id
}

# for example uploads bucket name is what you use when running terraform output
# description is just for someone reading the configuration not for command output
# value is what is actually seen

output "uploads_kms_key_arn" {
  description = "ARN of the KMS key used for S3 encryption"
  value       = aws_kms_key.uploads.arn
}

output "table_kms_key_arn" {
  description = "ARN of the KMS key used for DynamoDB encryption"
  value       = aws_kms_key.table.arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the IAM role for API Lambda functions"
  value       = aws_iam_role.lambda_execution.arn
}

output "processing_lambda_role_arn" {
  description = "ARN of the IAM role for Processing Lambda functions"
  value       = aws_iam_role.processing_lambda.arn
}

output "step_functions_role_arn" {
  description = "ARN of the IAM role for Step Functions execution"
  value       = aws_iam_role.step_functions.arn
}

output "scheduler_role_arn" {
  description = "ARN of the IAM role for EventBridge Scheduler"
  value       = aws_iam_role.scheduler.arn
}

output "waf_web_acl_arn" {
  description = "ARN of the WAF WebACL attached to CloudFront"
  value       = aws_wafv2_web_acl.main.arn
}

output "ssm_parameter_paths" {
  description = "Map of SSM parameter paths that CDK reads at synth time"

  value = {
    uploads_bucket_name        = "/sfi/${local.env}/uploads-bucket-name"
    processed_bucket_name      = "/sfi/${local.env}/processed-bucket-name"
    uploads_bucket_arn         = "/sfi/${local.env}/uploads-bucket-arn"
    uploads_kms_key_arn        = "/sfi/${local.env}/uploads-kms-key-arn"
    table_kms_key_arn          = "/sfi/${local.env}/table-kms-key-arn"
    lambda_execution_role_arn  = "/sfi/${local.env}/lambda-execution-role-arn"
    processing_lambda_role_arn = "/sfi/${local.env}/processing-lambda-role-arn"
    stepfunctions_role_arn     = "/sfi/${local.env}/stepfunctions-role-arn"
    scheduler_role_arn         = "/sfi/${local.env}/scheduler-role-arn"
    waf_web_acl_arn            = "/sfi/${local.env}/waf-web-acl-arn"
  }

  # this differs than the ones above because value is an object 
  # inside objects each line has the key=value structure
  # after running terraform output ssm_parameter_paths you see all 10 keys and values
}