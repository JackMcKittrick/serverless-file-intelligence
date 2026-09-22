# terraform/variables.tf
# =======================
# Input variables for the Terraform foundation layer.
# Copy terraform.tfvars.example → terraform.tfvars and fill in your values.
#
# WHAT TO BUILD — declare each variable block:
#
# variable "environment"
#   type        = string
#   description = "Deployment environment"
#   validation: must be one of dev, staging, prod
#
# variable "aws_region"
#   type        = string
#   default     = "us-east-1"
#   description = "AWS region for the primary provider"
#
# variable "account_id"
#   type        = string
#   description = "12-digit AWS account ID — used in bucket names for global uniqueness"
#   NO default — must be supplied explicitly so it is never accidentally omitted
#   WHY: S3 bucket names are global. Including account_id prevents naming collisions
#        and makes bucket names predictable from just the environment.
#
# variable "kms_deletion_window_days"
#   type    = number
#   default = 7
#   description = "Days before a scheduled KMS key deletion becomes effective (7-30)"
#
# variable "s3_glacier_transition_days"
#   type    = number
#   default = 90
#   description = "Days after upload before moving objects to Glacier IR storage class"
#
# variable "s3_expiration_days"
#   type    = number
#   default = 365
#   description = "Days after upload before uploads bucket objects expire"
#
# variable "processed_expiration_days"
#   type    = number
#   default = 90
#   description = "Days after creation before processed-results objects expire"

# TODO: implement the variable blocks described above
