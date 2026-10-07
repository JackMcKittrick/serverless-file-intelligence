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

resource "aws_kms_key" "uploads" {

  # learned resource block syntax is 
  # resource "provider_resource_type" "localname" {}

  # this is a customer managed key bc you wouldnt create a resource if not

  description             = "SFI uploads S3 encryption key - ${local.env}"
  deletion_window_in_days = var.kms_deletion_window_days   # use variable just wrote in variables file 
  enable_key_rotation     = true 
  # aws can rotate cyprographic key bc even though its a cmk, aws will still generate a key unless explicitly upload a key

  # NOTE
  # Terraform compares the current state to the desired configuration. If a resource's name or settings 
  # change in a way that requires replacement, Terraform plans to delete the old resource and create a new one to match the configuration.
  # got a little confused with env variable bc thought thatd create duplicate resources but not the case 


  # obviously terraform written in HCL not JSON so 
  # instead of writting JSON manually you can create a terraform object
  # and this function will covert it to valid JSON
  policy = jsonencode({
    Version = "2012-10-17"   # actually not when written its standard policy syntax

    # the [] mean a list
    # each {} inside the list is one permission rule
    Statement = [

      { 
        Sid    = "AllowRoot"
        Effect = "Allow"

        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },  
      # The root/account statement in a KMS key policy does not give every IAM user or role access to the key
      # instead it tells KMS to consider IAM permissions that are granted within that AWS account
      # without this statement, KMS may ignore IAM policies and require users and roles to be explicitly listed in the key policy before they can use the key
      # with the statement in place, administrators can grant permissions such as kms:Encrypt and kms:Decrypt through standard IAM policies, and KMS will evaluate those permissions when determining access
      # this makes key management much easier because access can be controlled through IAM policies rather than continuously updating the key policy for every new user or role
      # got confused and forgot this
      {
        Sid    = "AllowS3Service"
        Effect = "Allow"

        Principal = {
          Service = "s3.amazonaws.com"
        }

        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
        ]

        Resource = "*"
      },
      {
        Sid    = "AllowLambdaDecrypt"
        Effect = "Allow"

        Principal = {
          AWS = aws_iam_role.lambda_execution.arn
        }

        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]

        Resource = "*"
      }, # .arn in terraform gets the ARN of IAM role needing to read encrypted files
    ]
  })
}

resource "aws_kms_alias" "uploads" {
  name          = "alias/sfi-${local.env}-uploads"
  target_key_id = aws_kms_key.uploads.key_id
} # learned that alias/ is required, this makes friendly name for key 


# basically same thing as the kms key but for dynamo db
resource "aws_kms_key" "table" {
  description             = "SFI DynamoDB encryption key - ${local.env}"
  deletion_window_in_days = var.kms_deletion_window_days
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "AllowRoot"
        Effect = "Allow"

        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }

        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowDynamoDBService"
        Effect = "Allow"

        Principal = {
          Service = "dynamodb.amazonaws.com"
        }

        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
        ]

        Resource = "*"
      },
      {
        Sid    = "AllowLambdaDecrypt"
        Effect = "Allow"

        Principal = {
          AWS = aws_iam_role.lambda_execution.arn
        }

        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]

        Resource = "*"
      },
    ]
  })
}

# another friendly alias for key
resource "aws_kms_alias" "table" {
  name          = "alias/sfi-${local.env}-table"
  target_key_id = aws_kms_key.table.key_id
}

# below not trying to keep arns secret but to avoid hardcoding use ssm
# while this terraform project knows aws_kms_key.uploads.arn
# CDK can read this SSM parameter at synth time and import the Terraform-owned key
resource "aws_ssm_parameter" "uploads_kms_key_arn" {
  name  = "/sfi/${local.env}/uploads-kms-key-arn"
  type  = "String"
  value = aws_kms_key.uploads.arn
}

resource "aws_ssm_parameter" "table_kms_key_arn" {
  name  = "/sfi/${local.env}/table-kms-key-arn"
  type  = "String"
  value = aws_kms_key.table.arn
}