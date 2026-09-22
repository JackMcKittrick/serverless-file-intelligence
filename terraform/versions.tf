# terraform/versions.tf
# ======================
# Pin provider versions and configure the remote state backend.
#
# WHAT TO BUILD:
#
# STEP 1 — terraform block
#   Set required_version = "~> 1.7"
#   required_providers:
#     aws = { source = "hashicorp/aws", version = "~> 5.40" }
#
# STEP 2 — S3 remote state backend (comment out until you bootstrap the bucket)
#   backend "s3" {
#     bucket         = "sfi-terraform-state-<YOUR-ACCOUNT-ID>"
#     key            = "sfi/${var.environment}/terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "sfi-terraform-locks"
#     encrypt        = true
#   }
#   WHY: Remote state lets multiple developers/CI share the same state file safely.
#        DynamoDB provides state locking so two applies never run simultaneously.
#        DO NOT commit terraform.tfstate to git — the S3 backend keeps it out.
#
# STEP 3 — Default AWS provider with default_tags
#   provider "aws" {
#     region = var.aws_region
#     default_tags { tags = { Project = "sfi", Environment = var.environment, ManagedBy = "Terraform" } }
#   }
#   WHY: default_tags apply to EVERY resource in this config automatically —
#        you never forget to tag something.
#
# STEP 4 — US East 1 provider alias (for WAF — CloudFront scope requires us-east-1)
#   provider "aws" {
#     alias  = "us_east_1"
#     region = "us-east-1"
#   }
#   WHY: CloudFront WAF WebACLs can only exist in us-east-1 even if your main
#        region is different. The alias lets you target us-east-1 for just waf.tf.
#
# STEP 5 — locals block (used throughout all .tf files)
#   locals {
#     env         = var.environment
#     account_id  = var.account_id
#     region      = var.aws_region
#     name_prefix = "sfi-${var.environment}"
#   }

# TODO: implement the blocks described above
