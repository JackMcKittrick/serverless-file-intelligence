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

variable "environment" {
  type        = string
  description = "Deployment environment"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }

  # learned this cool allow list to ensure one of three strings

}

# ok so i learned variable syntax is 
# variable "variable_name"
# also type tells terraform what kind of value is expected can be string, number, etc 
# default is an optional field but used if user doesn't provide one
# description is optional as well good for documentation
# validation is optional it helps reject bad values

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for the primary provider"
}

# self explanitory, want to avoid hard coding region

variable "account_id" {
  type        = string
  description = "12-digit AWS account ID used in bucket names for global uniqueness"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }

  # the regex statement ensures that account id is 12 numbers 0-9
  # returns an error so can makes it return true or false
  # purpose bc s3 buckets globally unique common to use account numbers
  # thought unsafe but for examples roles include them so aws doesn't treat as secrets
}

variable "kms_deletion_window_days" {
  type        = number
  default     = 7
  description = "Days before a scheduled KMS key deletion becomes effective (7-30)"

  validation {
    condition     = var.kms_deletion_window_days >= 7 && var.kms_deletion_window_days <= 30
    error_message = "kms_deletion_window_days must be between 7 and 30."
  }
}

# from certs i know aws has 7 to 30 wait period for key deletion

variable "s3_glacier_transition_days" {
  type        = number
  default     = 90
  description = "Days after upload before moving objects to Glacier IR storage class"

  validation {
    condition     = var.s3_glacier_transition_days > 0
    error_message = "s3_glacier_transition_days must be greater than 0."
  }
}

# 90 days until s3 goes to glacier

variable "s3_expiration_days" {
  type        = number
  default     = 365
  description = "Days after upload before uploads bucket objects expire"

  validation {
    condition     = var.s3_expiration_days > 0
    error_message = "s3_expiration_days must be greater than 0."
  }
}

# this variable will be enforced by lifecycle rule
# uploaded objs will be deleted after 365 days

variable "processed_expiration_days" {
  type        = number
  default     = 90
  description = "Days after creation before processed-results objects expire"

  validation {
    condition     = var.processed_expiration_days > 0
    error_message = "processed_expiration_days must be greater than 0."
  }
}

# for the outputs we don't need to hold longterm so shorter deletion time