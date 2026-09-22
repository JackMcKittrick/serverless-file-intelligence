# terraform/kms.tf
# ==================
# Two KMS customer-managed keys: one for S3 buckets, one for DynamoDB.
# KMS keys stay in Terraform — never in CDK — so cdk destroy can never delete them.
#
# WHAT TO BUILD:
#
# RESOURCE 1 — aws_kms_key "uploads" (for S3 encryption)
#   description             = "SFI uploads S3 encryption key - ${local.env}"
#   deletion_window_in_days = var.kms_deletion_window_days
#   enable_key_rotation     = true     ← REQUIRED: rotate annually, no extra cost
#   policy = jsonencode({              ← key policy JSON
#     Version   = "2012-10-17"
#     Statement = [
#       # Allow root account full control (required so the key isn't locked out)
#       { Sid = "AllowRoot", Effect = "Allow",
#         Principal = {AWS = "arn:aws:iam::${local.account_id}:root"},
#         Action = "kms:*", Resource = "*" },
#       # Allow S3 service to use the key for encryption/decryption
#       { Sid = "AllowS3Service", Effect = "Allow",
#         Principal = {Service = "s3.amazonaws.com"},
#         Action = ["kms:GenerateDataKey", "kms:Decrypt"], Resource = "*" },
#       # Allow the Lambda execution role to decrypt (to read uploaded files)
#       { Sid = "AllowLambdaDecrypt", Effect = "Allow",
#         Principal = {AWS = aws_iam_role.lambda_execution.arn},
#         Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = "*" },
#     ]
#   })
#
# RESOURCE 2 — aws_kms_alias for uploads key
#   name          = "alias/sfi-${local.env}-uploads"
#   target_key_id = aws_kms_key.uploads.key_id
#
# RESOURCE 3 — aws_kms_key "table" (for DynamoDB encryption)
#   Same structure as uploads key, but:
#   - description uses "DynamoDB"
#   - S3 service principal → DynamoDB service principal:
#     { Service = "dynamodb.amazonaws.com" }
#
# RESOURCE 4 — aws_kms_alias for table key
#   name = "alias/sfi-${local.env}-table"
#
# RESOURCE 5 — aws_ssm_parameter for uploads key ARN
#   name  = "/sfi/${local.env}/uploads-kms-key-arn"
#   type  = "String"
#   value = aws_kms_key.uploads.arn
#   WHY: CDK reads this at synth time to import the key as an IKey reference.
#
# RESOURCE 6 — aws_ssm_parameter for table key ARN
#   name  = "/sfi/${local.env}/table-kms-key-arn"
#   value = aws_kms_key.table.arn

# TODO: implement the resources described above
