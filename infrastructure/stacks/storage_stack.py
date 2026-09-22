"""
infrastructure/stacks/storage_stack.py
========================================
CDK stack: imports Terraform-managed S3/KMS from SSM, creates DynamoDB + CloudFront.

DEPLOY ORDER: terraform apply (Phase 1) → cdk deploy StorageStack (Phase 4)

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Read Terraform outputs from SSM Parameter Store
  Use ssm.StringParameter.value_from_lookup() for each:
    /sfi/{env}/uploads-bucket-name
    /sfi/{env}/processed-bucket-name
    /sfi/{env}/uploads-kms-key-arn
    /sfi/{env}/table-kms-key-arn
    /sfi/{env}/waf-web-acl-arn
  WHY: value_from_lookup() resolves at CDK synth time and caches in cdk.context.json.
       After the first run CDK synth works offline. Terraform writes these params;
       CDK reads them — neither tool needs the other's state files.

STEP 2 — Import S3 buckets as IBucket references (no ownership)
  self._uploads_bucket   = s3.Bucket.from_bucket_name(self, "UploadsBucket", uploads_bucket_name)
  self._processed_bucket = s3.Bucket.from_bucket_name(self, "ProcessedBucket", processed_bucket_name)
  WHY: from_bucket_name() gives CDK a handle for grants/notifications without
       putting the bucket in CDK state. cdk destroy will NEVER delete these buckets.

STEP 3 — Import KMS keys as IKey references
  self._uploads_kms_key = kms.Key.from_key_arn(self, "UploadsKMSKey", uploads_kms_key_arn)
  self._table_kms_key   = kms.Key.from_key_arn(self, "TableKMSKey", table_kms_key_arn)

STEP 4 — Enable EventBridge notifications on the uploads bucket
  self._uploads_bucket.enable_event_bridge_notification()
  WHY: This puts a bucket notification config that routes ObjectCreated events
       to the default EventBridge bus. The EventBridge → SQS → Step Functions
       trigger chain starts here.

STEP 5 — Create the DynamoDB files table
  dynamodb.Table with:
    table_name = f"sfi-files-{environment}"
    partition_key = Attribute(name="PK", type=STRING)
    sort_key      = Attribute(name="SK",  type=STRING)
    billing_mode  = PAY_PER_REQUEST
    encryption    = CUSTOMER_MANAGED, encryption_key = self._table_kms_key
    stream        = NEW_AND_OLD_IMAGES   ← feeds WebSocket push Lambda
    time_to_live_attribute = "ttl"
    removal_policy = RETAIN             ← never destroy the table
    point_in_time_recovery = True
  WHY: Single-table design stores files (PK=USER#<id>, SK=FILE#<id>) and
       WebSocket connections (PK=USER#<id>, SK=CONN#<id>). PAY_PER_REQUEST
       eliminates capacity planning for a portfolio project.

STEP 6 — Add Global Secondary Indexes
  StatusIndex: PK=processingStatus (STRING), SK=uploadedAt (STRING), projection=ALL
    WHY: Housekeeping Lambda queries PENDING/PROCESSED files without full table scan.
  FileTypeIndex: PK=contentType (STRING), SK=uploadedAt (STRING), projection=KEYS_ONLY
    WHY: Optional analytics — count uploads by file type.

STEP 7 — Create the CloudFront distribution for the frontend
  a. Create a new S3 bucket for frontend assets (CDK-managed, DESTROY policy)
  b. Create an S3OriginAccessControl (OAC) — NOT the deprecated OAI
  c. Create a CloudFront Distribution:
       default_behavior: S3BucketOrigin.with_origin_access_control(frontend_bucket, oac)
       viewer_protocol_policy: REDIRECT_TO_HTTPS
       cache_policy: CACHING_OPTIMIZED
       web_acl_id: waf_web_acl_arn   ← from SSM (Terraform-managed)
       error_responses: [404 → index.html / 200]  ← SPA client-side routing
       default_root_object: "index.html"
  WHY: CloudFront serves the SPA globally with edge caching. OAC (not OAI) is
       the current AWS-recommended way to authorize CloudFront → S3 access.

STEP 8 — CfnOutputs + Python properties
  Outputs: FilesTableName, FilesTableArn, CloudFrontUrl, FrontendBucketName
  Properties (used in app.py to wire stacks together):
    uploads_bucket, processed_bucket, files_table, uploads_kms_key, distribution
"""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class StorageStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # TODO: implement Steps 1-8 described above

    @property
    def uploads_bucket(self) -> s3.IBucket:
        raise NotImplementedError("Implement Step 2 first")

    @property
    def processed_bucket(self) -> s3.IBucket:
        raise NotImplementedError("Implement Step 2 first")

    @property
    def files_table(self) -> dynamodb.Table:
        raise NotImplementedError("Implement Step 5 first")

    @property
    def uploads_kms_key(self) -> kms.IKey:
        raise NotImplementedError("Implement Step 3 first")

    @property
    def distribution(self) -> cloudfront.Distribution:
        raise NotImplementedError("Implement Step 7 first")
