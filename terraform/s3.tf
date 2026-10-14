# terraform/s3.tf
# =================
# Two S3 buckets — uploads and processed — plus SSM parameters for bucket names.
# Buckets stay in Terraform (not CDK) so that cdk destroy can NEVER delete
# user-uploaded files or processed results.
#
# WHAT TO BUILD:
#
# ── RESOURCE 1: aws_s3_bucket "uploads" ──────────────────────────────────────
#   resource "aws_s3_bucket" "uploads" {
#     bucket = "sfi-uploads-${local.env}-${local.account_id}"
#   }
#   WHY: Including account_id makes the name globally unique and predictable.
#
# ── RESOURCE 2: aws_s3_bucket_versioning "uploads" ───────────────────────────
#   resource "aws_s3_bucket_versioning" "uploads" {
#     bucket = aws_s3_bucket.uploads.id
#     versioning_configuration { status = "Enabled" }
#   }
#   WHY: Versioning allows accidental-delete recovery without extra infrastructure.
#
# ── RESOURCE 3: aws_s3_bucket_server_side_encryption_configuration "uploads" ─
#   resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
#     bucket = aws_s3_bucket.uploads.id
#     rule {
#       apply_server_side_encryption_by_default {
#         sse_algorithm     = "aws:kms"
#         kms_master_key_id = aws_kms_key.uploads.arn
#       }
#       bucket_key_enabled = true   ← REQUIRED: reduces KMS API costs by ~99%
#     }
#   }
#
# ── RESOURCE 4: aws_s3_bucket_public_access_block "uploads" ──────────────────
#   All four block settings = true:
#     block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets
#   WHY: No user file should EVER be publicly accessible. Defense-in-depth.
#
# ── RESOURCE 5: aws_s3_bucket_cors_configuration "uploads" ───────────────────
#   cors_rule {
#     allowed_headers = ["*"]
#     allowed_methods = ["PUT"]           ← Only PUT — for presigned upload URLs
#     allowed_origins = ["*"]             ← Tighten to your domain in production
#     expose_headers  = ["ETag"]
#     max_age_seconds = 3600
#   }
#   WHY: Without CORS, the browser's fetch() call for the presigned PUT will fail.
#
# ── RESOURCE 6: aws_s3_bucket_lifecycle_configuration "uploads" ──────────────
#   resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
#     bucket = aws_s3_bucket.uploads.id
#     rule {
#       id     = "archive-and-expire"
#       status = "Enabled"
#       filter { prefix = "" }    ← applies to all objects
#       transition {
#         days          = var.s3_glacier_transition_days    ← default 90
#         storage_class = "GLACIER_IR"
#       }
#       expiration {
#         days = var.s3_expiration_days                     ← default 365
#       }
#     }
#   }
#   WHY: Glacier IR (Instant Retrieval) cuts storage cost ~70% for rarely-accessed
#        files while keeping millisecond retrieval for the rare user download.
#
# ── RESOURCE 7: aws_s3_bucket_notification "uploads" ─────────────────────────
#   Enable EventBridge notifications so S3 events flow to EventBridge:
#   resource "aws_s3_bucket_notification" "uploads" {
#     bucket      = aws_s3_bucket.uploads.id
#     eventbridge = true
#   }
#   WHY: The CDK ProcessingStack creates an EventBridge rule that triggers the
#        processing pipeline. S3 must have EventBridge notifications enabled.
#
# ── RESOURCE 8: lifecycle meta-argument on aws_s3_bucket "uploads" ────────────
#   Add inside the resource block:
#   lifecycle {
#     prevent_destroy = true
#   }
#   WHY: terraform destroy will fail rather than delete user files. Remove this
#        block ONLY when intentionally tearing down the entire environment.
#
# ── RESOURCE 9: aws_s3_bucket "processed" ────────────────────────────────────
#   bucket = "sfi-processed-${local.env}-${local.account_id}"
#   Same encryption as uploads bucket (use aws_kms_key.uploads.arn — same key)
#   Same public access block (all four = true)
#   Lifecycle: single expiration rule
#     days = var.processed_expiration_days    ← default 90
#     (no glacier transition — results are accessed actively or not at all)
#   lifecycle { prevent_destroy = true }
#   NO versioning, NO CORS, NO EventBridge
#   WHY: Processed results live for 90 days then expire. No versioning needed
#        because these are derived/generated files, not originals.
#
# ── RESOURCE 10: aws_ssm_parameter "uploads_bucket_name" ─────────────────────
#   name  = "/sfi/${local.env}/uploads-bucket-name"
#   type  = "String"
#   value = aws_s3_bucket.uploads.id
#   WHY: CDK StorageStack reads this at synth time via
#        ssm.StringParameter.value_from_lookup() to import the bucket without
#        owning it. Bucket names (not ARNs) are what Bucket.from_bucket_name() needs.
#
# ── RESOURCE 11: aws_ssm_parameter "processed_bucket_name" ───────────────────
#   name  = "/sfi/${local.env}/processed-bucket-name"
#   value = aws_s3_bucket.processed.id
#
# ── RESOURCE 12: aws_ssm_parameter "uploads_bucket_arn" ──────────────────────
#   name  = "/sfi/${local.env}/uploads-bucket-arn"
#   value = aws_s3_bucket.uploads.arn
#   WHY: Some IAM policies and CDK constructs need the full ARN, not just the name.

# TODO: implement the 12 resources described above

resource "aws_s3_bucket" "uploads" {
  bucket = "sfi-uploads-${local.env}-${local.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

# this gonna be where original user uploaded files go
# using the acc number in s3 bucket again so globally unique
# the lifecycle destroy prevention only applies to terraform
# for true deletion protection id use object lock or IAM etc  

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
    # a reference to the bucket above
  versioning_configuration {
    status = "Enabled"
  }
}

# turns on versioning for the uploads bucket so if file overwritten or deleted s3 
# s3 has previous versions
# the bucket syntax is resource type then resource name then id which is usually bucket name

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.uploads.arn
    }

    bucket_key_enabled = true
  }
}

# here aws:kms means using a kms managed encryption compared to s3 managed
# then I point to the kms key i created in kms.tf
# bucket key enabled instead of calling kms for each object
# to save money s3 gets a bucket key which is cached and can dervice object keys
# rule{} is just nested block for this resource you don't normally see multiple rules

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# great security measure for blocking public access
# for example the public policy one stops someone from attaching
# a bucket policy with principle "*"
# ACLs for s3 are old nowadays its iam bucket policies and access points
# aws actually recommends for you to disable

# relearned access points
# instead of a bucket with a giant bucket policy
# you have smaller access points with smaller policies
# for normal bucket access you can just reference the name or ARN
# for access points it has it own ARN you reference

resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# cross origin is when hostnames differ or protocols or protocols
# so security in your broswer enforces that responses from different origins are blocked
# above s3 tells your browser that you are allowed to make the request
# cors is needed bc applicatino uses presigned urls
# without presigned urls the flow is normally browser, backend, s3
# but in this app the backend is generating a presigned url to return to broswer
# presigned urls super common for serverless applications bc lambda wont touch the file it just processes URL so less cost

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "archive-and-expire"
    status = "Enabled"

    filter {
      prefix = ""
    }

    transition {
      days          = var.s3_glacier_transition_days
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = var.s3_expiration_days
    }
  }
}

# these rules apply to all objects bc of empty string prefix
# tells s3 to move objs to glacier then delete over time

resource "aws_s3_bucket_notification" "uploads" {
  bucket      = aws_s3_bucket.uploads.id
  eventbridge = true
}

# critical here for the pipeline it enables s3 events into eventbridge
# example s3 can emit a Object Created and there will be eventbridge rule for that

resource "aws_s3_bucket" "processed" {
  bucket = "sfi-processed-${local.env}-${local.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

# creates s3 bucket for the output files

resource "aws_s3_bucket_server_side_encryption_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.uploads.arn
    }

    bucket_key_enabled = true
  }
}

# same encryption idea as before

resource "aws_s3_bucket_public_access_block" "processed" {
  bucket = aws_s3_bucket.processed.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# same security idea as before

resource "aws_s3_bucket_lifecycle_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id

  rule {
    id     = "expire-processed-results"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = var.processed_expiration_days
    }
  }
}

# no glacier here bc don't need output for long

# below similar to other previous written files
# ssm strings for CDK to use

resource "aws_ssm_parameter" "uploads_bucket_name" {
  name  = "/sfi/${local.env}/uploads-bucket-name"
  type  = "String"
  value = aws_s3_bucket.uploads.id
}

resource "aws_ssm_parameter" "processed_bucket_name" {
  name  = "/sfi/${local.env}/processed-bucket-name"
  type  = "String"
  value = aws_s3_bucket.processed.id
}

resource "aws_ssm_parameter" "uploads_bucket_arn" {
  name  = "/sfi/${local.env}/uploads-bucket-arn"
  type  = "String"
  value = aws_s3_bucket.uploads.arn
}