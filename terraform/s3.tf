# terraform/s3.tf
# =================
# Two S3 buckets — uploads and processed — plus SSM parameters for bucket names.

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