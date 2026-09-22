# Serverless File Intelligence — Implementation Guide

This guide walks you through building the entire project from scratch, in the exact order
dependencies require. Complete each phase fully before moving to the next.

---

## Prerequisites

Install these tools before starting:

- AWS CLI v2 (`aws --version`)
- Terraform >= 1.7 (`terraform --version`)
- Python 3.11 (`python3 --version`)
- Node.js 20+ (`node --version`) — needed for AWS CDK
- AWS CDK v2 (`npm install -g aws-cdk`, then `cdk --version`)
- Git

Configure your AWS credentials (`aws configure`) and verify with `aws sts get-caller-identity`.

---

## Phase 1 — Terraform Foundation

The Terraform layer creates long-lived, security-critical resources that CDK must never own
or destroy: S3 buckets, KMS keys, IAM roles, and WAF. Complete all of Phase 1 and run
`terraform apply` before touching any CDK code.

### Step 1.1 — terraform/versions.tf

Open `terraform/versions.tf` and follow the instructions inside.

What you are building:
- `terraform` block pinning provider versions and (optionally) configuring remote state
- Default `aws` provider with `default_tags` so every resource is auto-tagged
- `aws.us_east_1` provider alias (required for WAF — CloudFront WAF must be us-east-1)
- `locals` block that shorthand variables all other `.tf` files use

After writing: `terraform init` to download the AWS provider. Fix any version errors before continuing.

### Step 1.2 — terraform/variables.tf

Open `terraform/variables.tf` and follow the instructions inside.

What you are building:
- `environment` variable with validation (dev / staging / prod only)
- `aws_region` with default `us-east-1`
- `account_id` with NO default — must be supplied explicitly
- Four numeric variables for KMS deletion window and S3 lifecycle thresholds

After writing: Copy `terraform.tfvars.example` → `terraform.tfvars` and fill in your real values.
Run `terraform validate` to catch syntax errors.

### Step 1.3 — terraform/kms.tf

Open `terraform/kms.tf` and follow the instructions inside.

What you are building:
- `aws_kms_key.uploads` — key for S3 encryption, with key policy granting root, S3 service,
  and the lambda_execution role (you will create the role in Step 1.4, so reference it there)
- `aws_kms_alias.uploads`
- `aws_kms_key.table` — key for DynamoDB encryption
- `aws_kms_alias.table`
- Two `aws_ssm_parameter` resources storing key ARNs for CDK to read

Important: `enable_key_rotation = true` is required on both keys.

### Step 1.4 — terraform/iam.tf

Open `terraform/iam.tf` and follow the instructions inside.

What you are building (4 roles):
1. `lambda_execution` — API Lambdas: DynamoDB CRUD, S3 read/write, SSM GetParameter, KMS, CloudWatch Logs, X-Ray
2. `processing_lambda` — everything in Role 1 plus Textract, Rekognition, Comprehend, Bedrock, SNS
3. `step_functions` — InvokeFunction on `sfi-*` Lambdas, Step Functions log delivery, X-Ray
4. `scheduler` — InvokeFunction on ONLY the housekeeping Lambda

Plus 4 `aws_ssm_parameter` resources (one per role ARN) so CDK can import them.

Note: `kms.tf` references `aws_iam_role.lambda_execution.arn` in the key policy.
Terraform resolves cross-resource references automatically — no ordering needed.

### Step 1.5 — terraform/s3.tf

Open `terraform/s3.tf` and follow the instructions inside.

What you are building:
- `aws_s3_bucket.uploads` with versioning, KMS encryption (bucket key enabled), public access block,
  CORS for PUT only, lifecycle transitions to Glacier IR, EventBridge notifications enabled,
  and `lifecycle { prevent_destroy = true }`
- `aws_s3_bucket.processed` — similar but no versioning, no CORS, no EventBridge, expiration only
- Three `aws_ssm_parameter` resources for bucket name and ARN

Critical: the `eventbridge = true` flag on `aws_s3_bucket_notification` is what allows the CDK
ProcessingStack's EventBridge rule to receive S3 events. Without it the pipeline never triggers.

### Step 1.6 — terraform/waf.tf

Open `terraform/waf.tf` and follow the instructions inside.

What you are building:
- `aws_wafv2_web_acl.main` with `provider = aws.us_east_1` and `scope = "CLOUDFRONT"`
  - Rule 1: AWS Managed Common Rule Set (OWASP Top 10)
  - Rule 2: AWS Managed Known Bad Inputs (log4shell, SSRF, etc.)
  - Rule 3: Rate limit — 1000 requests per 5 minutes per IP, action = block
- `aws_ssm_parameter` for the WAF ARN (also in us-east-1 provider)

Do NOT forget `provider = aws.us_east_1` on both resources. AWS rejects CLOUDFRONT-scope WAF
outside us-east-1 with a confusing error.

### Step 1.7 — terraform/outputs.tf

Open `terraform/outputs.tf` and follow the instructions inside.

What you are building:
- 10 Terraform outputs: bucket names, KMS key ARNs, IAM role ARNs, WAF ARN, SSM path map

These are for human operators. The actual CDK handoff happens via SSM parameters (created
alongside each resource in the previous steps).

### Step 1.8 — Bootstrap Terraform Remote State (optional but recommended)

If you want shared remote state (needed for team use or CI):

```bash
# Create the state bucket and lock table ONCE (do this before any apply):
aws s3api create-bucket --bucket sfi-terraform-state-<YOUR-ACCOUNT-ID> --region us-east-1
aws s3api put-bucket-versioning --bucket sfi-terraform-state-<YOUR-ACCOUNT-ID> \
    --versioning-configuration Status=Enabled
aws dynamodb create-table \
    --table-name sfi-terraform-locks \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1
```

Then uncomment the `backend "s3"` block in `versions.tf` and run `terraform init -migrate-state`.

### Step 1.9 — Apply Terraform

```bash
cd terraform
terraform plan -out=tfplan          # Review — confirm only new resources, no replacements
terraform apply tfplan
terraform output -json ssm_parameter_paths  # Verify all SSM paths are populated
```

Verify in AWS Console → SSM Parameter Store that all `/sfi/dev/*` parameters exist.
You must complete this step before any CDK stack can synthesize.

---

## Phase 2 — Shared Lambda Layer

The Lambda layer is a Python package deployed to all functions. Build it before any CDK stack
that creates Lambda functions.

### Step 2.1 — backend/layers/shared/python/error_types.py

Open the file and follow the numbered STEP comments inside.

What you are building:
- `SFIError(Exception)` — base class with `message`, `status_code`, `error_code`, `to_dict()`
- Five subclasses: `ValidationError` (400), `NotFoundError` (404), `AuthorizationError` (403),
  `ConflictError` (409), `ProcessingError` (422)

These are imported by every Lambda handler. Get them right before moving forward.

### Step 2.2 — backend/layers/shared/python/response_helpers.py

Open the file and follow the numbered STEP comments inside.

What you are building:
- `CORS_HEADERS` dict — every API response must include these or the browser blocks it
- `success(body, status_code=200)` — returns standard API Gateway proxy response dict
- `error(sfi_error)` — converts an SFIError to an API Gateway proxy response
- `paginated(items, next_key, limit)` — success response with pagination metadata
- `extract_user_id(event)` — reads Cognito sub from the JWT claims in the event context

Key detail: `extract_user_id` reads `event["requestContext"]["authorizer"]["claims"]["sub"]`.
This path is set by the API Gateway Cognito authorizer — do not change the path.

### Step 2.3 — backend/layers/shared/python/dynamo_client.py

Open the file and follow the numbered STEP comments inside.

What you are building:
- Module-level boto3 resource and `TABLE_NAME = os.environ["TABLE_NAME"]`
- Key helpers: `PK(user_id)`, `SK_FILE(file_id)`, `SK_CONN(connection_id)`
- `get_file(user_id, file_id)` → raises `NotFoundError` if missing
- `list_user_files(user_id, limit, last_key)` → returns `(items, next_key)` tuple
- `put_file(item_dict)` — writes a new file record
- `update_file_status(user_id, file_id, status, **extra_fields)` — UpdateExpression
- `delete_file_record(user_id, file_id)` — DeleteItem

All DynamoDB operations use `PK=USER#{user_id}` and `SK=FILE#{file_id}` key patterns.

---

## Phase 3 — Lambda Function Handlers

Write each handler in isolation. The `dynamo_client` and `response_helpers` imports are
provided by the shared layer at runtime — do not copy-paste the layer code into handlers.

### Step 3.1 — backend/functions/get_upload_url/handler.py

Open the file and follow the STEP comments inside.

What you are building:
- Parse and validate the request body (fileName, contentType, fileSize; enforce 50MB limit)
- Check contentType is in the allowed set (PDF, PNG, JPG, GIF, WEBP)
- Generate `file_id = str(uuid.uuid4())`
- Build `s3_key = f"{user_id}/{file_id}/{file_name}"`
- Call `s3.generate_presigned_url("put_object", Params={...}, ExpiresIn=900)`
- Write a PENDING record to DynamoDB with a 24-hour TTL
- Return `{"uploadUrl": ..., "fileId": ..., "expiresIn": 900}`

Environment variables: `UPLOADS_BUCKET`, `TABLE_NAME`

### Step 3.2 — backend/functions/list_files/handler.py

Open the file and follow the STEP comments inside.

What you are building:
- Extract `userId` from the JWT sub claim
- Parse `?limit` query parameter (integer, max 100, default 20)
- Decode base64 `lastKey` query parameter if present (pagination cursor)
- Call `dynamo_client.list_user_files()`
- Strip internal fields (PK, SK, s3Key, userId, ttl) from response items
- Encode next_key as base64
- Return `paginated(items, next_key, limit)`

### Step 3.3 — backend/functions/get_file_results/handler.py

Open the file and follow the STEP comments inside.

What you are building:
- Extract `userId` and `fileId` from `event["pathParameters"]`
- Call `get_file()` — raises NotFoundError if missing or wrong owner
- If `processingStatus == "PROCESSED"`: generate a presigned GET URL from `PROCESSED_BUCKET`
  (60-second expiry — short enough to prevent sharing, long enough for the UI to use)
- Strip internal fields and return `success(item)`

Environment variables: `TABLE_NAME`, `PROCESSED_BUCKET`

### Step 3.4 — backend/functions/delete_file/handler.py

Open the file and follow the STEP comments inside.

What you are building:
- Extract userId + fileId
- `get_file()` to verify ownership and retrieve `s3Key`
- Delete the raw file from `UPLOADS_BUCKET` (this must succeed)
- Delete from `PROCESSED_BUCKET` — best-effort, catch and ignore `NoSuchKey`
- Delete the DynamoDB record
- Return `success({"message": "File deleted successfully"})`

### Step 3.5 — backend/functions/process_document/handler.py

Open the file and follow the STEP comments inside.

This is a Step Functions task Lambda, NOT an API handler. Input = the Step Functions
execution input dict. Output = enriched dict passed to the next state.

What you are building:
- `update_file_status(user_id, file_id, "PROCESSING")`
- Call Textract `detect_document_text` with the S3 object location
- Extract LINE blocks from the response, join with "\n" → `extracted_text`
- Call Comprehend `detect_entities` (truncate input to 5000 chars), filter Score >= 0.80
- Return `{**event, "extractedText": extracted_text, "entities": [...]}`
- On any exception: `update_file_status(..., "FAILED")` then re-raise

### Step 3.6 — backend/functions/process_image/handler.py

Open the file and follow the STEP comments inside.

What you are building:
- `update_file_status(user_id, file_id, "PROCESSING")`
- Call Rekognition `detect_labels(MaxLabels=20, MinConfidence=70.0)` with S3 object
- Extract label names from the response
- Return `{**event, "labels": label_names_list}`
- On exception: update FAILED + re-raise

### Step 3.7 — backend/functions/ai_summarize/handler.py

Open the file and follow the STEP comments inside.

This is the LAST step in both pipelines (document and image). It calls Bedrock and writes
the final PROCESSED record.

What you are building:
- Choose prompt based on whether `event` contains `"extractedText"` (document) or `"labels"` (image)
- Truncate text/labels to 3000 chars for the prompt
- Call Bedrock `invoke_model` using the Anthropic message format:
  `{"anthropic_version": "bedrock-2023-05-31", "max_tokens": 500, "messages": [...]}`
- Parse the response JSON to extract the summary text
- Call `update_file_status(..., "PROCESSED", summary=summary, extractedText=..., labels=..., entities=...)`
- Return `{**event, "summary": summary}`

Environment variables: `TABLE_NAME`, `BEDROCK_MODEL_ID` (default: `"anthropic.claude-haiku-20240307-v1:0"`)

### Step 3.8 — backend/functions/websocket_handler/handler.py

Open the file and follow the STEP comments inside.

This handler serves THREE invocation sources via `event` inspection:

Route A — `$connect` (WebSocket connect):
- Read `connectionId` from `event["requestContext"]["connectionId"]`
- Read `userId` from `event["queryStringParameters"]["userId"]`
- Write `PK=USER#{userId}, SK=CONN#{connectionId}` record with 2-hour TTL
- Return `{"statusCode": 200}`

Route B — `$disconnect` (WebSocket disconnect):
- Delete the CONN# record for this connectionId

Route C — DynamoDB Stream:
- For each stream record where SK starts with `FILE#` and the status field changed:
  - Find all CONN# records for the file's userId
  - Call `apigatewaymanagementapi.post_to_connection` with the status update
  - If `GoneException`: the client disconnected — delete the stale CONN# record

Environment variables: `TABLE_NAME`, `WEBSOCKET_API_ID`, `WEBSOCKET_STAGE`

### Step 3.9 — backend/functions/housekeeping/handler.py

Open the file and follow the STEP comments inside.

This runs daily at 02:00 UTC via EventBridge Scheduler.

What you are building:
- Query `StatusIndex` GSI for records where `processingStatus = "PENDING"`,
  filter those older than 2 hours → delete them (they are stuck uploads)
- Query `StatusIndex` for `processingStatus = "PROCESSED"`,
  filter those older than 30 days → delete S3 files from both buckets and the DynamoDB record
- Return a summary dict with counts of what was cleaned up

---

## Phase 4 — Unit Tests

Write tests before CDK so you can validate logic without deploying.

### Step 4.1 — tests/unit/test_handlers.py

Open the file and follow the STEP comments inside.

What you are building (5 test classes using moto + pytest):
- `TestGetUploadUrl` — happy path, file too large, bad content type, missing fields, auth error
- `TestListFiles` — happy path with pagination, empty list, pagination cursor decoding
- `TestGetFileResults` — PENDING status, PROCESSED status (includes presigned URL), file not found, wrong user
- `TestDeleteFile` — happy path, file not found, S3 errors handled gracefully
- `TestHousekeeping` — stuck PENDING cleanup, old PROCESSED cleanup, nothing to clean

Pattern for each test class:
```python
@pytest.fixture(autouse=True)
def aws_setup():
    with moto.mock_aws():
        # create S3 buckets, DynamoDB table, set env vars
        yield
```

Run with: `pytest tests/unit/ -v`

---

## Phase 5 — CDK Stacks

CDK stacks must be written in the order they are listed — each depends on the previous.
Run `cdk synth` (no deploy) after each stack to catch import and configuration errors early.

### Step 5.1 — infrastructure/stacks/auth_stack.py

Open the file and follow the STEP comments inside.

What you are building:
- `UserPool` with email sign-in, strong password policy, `RemovalPolicy.RETAIN`
- `UserPoolClient` configured for PKCE authorization code grant (not implicit grant)
- Cognito Hosted UI domain
- `CfnOutput` for UserPoolId, ClientId, and the hosted UI URL
- Python properties: `user_pool` and `user_pool_client`

After writing: `cdk synth SfiAuthStack` — fix any import errors.

### Step 5.2 — infrastructure/stacks/storage_stack.py

Open the file and follow the STEP comments inside.

What you are building:
- Read 5 SSM parameters via `ssm.StringParameter.value_from_lookup()`
  (uploads bucket name, processed bucket name, uploads KMS ARN, table KMS ARN, WAF ACL ARN)
- Import buckets with `Bucket.from_bucket_name()` — CDK references them without owning them
- Import KMS keys with `Key.from_key_arn()`
- Enable EventBridge notifications on the uploads bucket reference
- Create the DynamoDB table (PAY_PER_REQUEST, customer-managed KMS, stream NEW_AND_OLD_IMAGES, RETAIN)
- Add two GSIs: `StatusIndex` (processingStatus + uploadedAt, ALL) and `FileTypeIndex` (contentType + uploadedAt, KEYS_ONLY)
- Create the frontend S3 bucket, Origin Access Control (OAC), and CloudFront distribution
  - Wire the WAF ARN to `web_acl_id`
  - Add a custom error response: 404 → index.html with status 200 (SPA routing)
- Properties: `table`, `uploads_bucket`, `processed_bucket`, `distribution`

After writing: `cdk synth SfiStorageStack`. The SSM lookups run here — if any SSM parameter
is missing you will get a "dummy value" warning. Fix by running `terraform apply` first.

### Step 5.3 — infrastructure/stacks/api_stack.py

Open the file and follow the STEP comments inside.

What you are building:
- Read the Lambda execution role ARN from SSM, import with `iam.Role.from_role_arn()`
- Create the shared Lambda layer (Python 3.11, `backend/layers/shared`)
- `make_function()` helper — returns a `Function` with these defaults:
  - Runtime: `PYTHON_3_11`, Architecture: `ARM_64`
  - X-Ray tracing enabled
  - Memory: 256 MB
  - Role: imported lambda_execution role
  - Common environment variables: TABLE_NAME, UPLOADS_BUCKET, PROCESSED_BUCKET
- Create 4 REST Lambda functions using `make_function()`:
  `get_upload_url`, `list_files`, `get_file_results`, `delete_file`
- Create the REST API with a Cognito authorizer
- Wire up 4 routes (POST /files/upload, GET /files, GET /files/{fileId}, DELETE /files/{fileId})
- Create the WebSocket API (`$connect`, `$disconnect` → websocket_handler)
- Add the DynamoDB stream event source to the websocket_handler
- Properties: `api`, `websocket_api`

After writing: `cdk synth SfiApiStack`

### Step 5.4 — infrastructure/stacks/processing_stack.py

Open the file and follow the STEP comments inside.

What you are building:
- Import the processing_lambda role and step_functions role from SSM
- Create 3 Step Functions task Lambdas: `process_document`, `process_image`, `ai_summarize`
  (using the processing_lambda role which has Textract/Rekognition/Comprehend/Bedrock perms)
- Build the Step Functions state machine (EXPRESS type):
  - `DetermineFileType` (Choice): if contentType contains "pdf" or "text" → ProcessDocument; else → ProcessImage
  - `ProcessDocument` → `Summarize`
  - `ProcessImage` → `Summarize`
  - `Summarize` → `Done`
  - Any Lambda error → `ProcessingFailed`
- Create an SQS queue + DLQ (3 max receives, 14-day retention on DLQ)
- Create an EventBridge rule: S3 ObjectCreated on `sfi-uploads-*` → SQS queue
- Create an SQS bridge Lambda that reads from SQS and starts Step Functions executions
- Properties: `state_machine`, `queue`

After writing: `cdk synth SfiProcessingStack`

### Step 5.5 — infrastructure/stacks/monitoring_stack.py

Open the file and follow the STEP comments inside.

What you are building:
- SNS topic + email subscription (email from `ALERT_EMAIL` env var)
- 3 CloudWatch alarms:
  1. API 5xx errors > 10 in 5 minutes
  2. Step Functions execution failures > 5 in 5 minutes
  3. DLQ messages visible > 0 (any failed SQS message is an alarm)
  All three alarm actions → the SNS topic
- CloudWatch Dashboard with 5 metric widgets:
  API request count, API latency, Step Functions executions (succeeded/failed),
  Lambda error rates, DLQ depth
- `CfnOutput` for the Dashboard URL

After writing: `cdk synth SfiMonitoringStack`

### Step 5.6 — infrastructure/app.py

Open the file and follow the STEP comments inside.

What you are building:
- `cdk.App()`
- All 5 stacks with explicit `env` (account + region from environment variables or CDK context)
- `add_dependency()` calls:
  - StorageStack depends on AuthStack (needs the user pool for Cognito authorizer)
  - ApiStack depends on StorageStack (needs the DynamoDB table and buckets)
  - ProcessingStack depends on StorageStack (same reason)
  - MonitoringStack depends on ApiStack and ProcessingStack (watches their resources)
- Environment tags: `Project=sfi`, `Environment=<env>`
- `app.synth()`

After writing: `cdk synth` (all stacks). All 5 stacks should synthesize without errors.

---

## Phase 6 — Frontend

### Step 6.1 — frontend/index.html

Open the file and follow the HTML comment inside.

What you are building:
- Auth screen (shown when logged out): email/password form → triggers Cognito Hosted UI redirect
- App header with user email display and logout button
- Drag-and-drop file upload zone with file type and size hint
- File list: cards showing fileName, processingStatus badge, uploadedAt date
- Results modal: summary text, extracted text or image labels, download button
- Toast notification area (for upload success/failure messages)

Status badge classes (must match styles.css): `.status-pending`, `.status-processing`,
`.status-processed`, `.status-failed`

### Step 6.2 — frontend/styles.css

Open the file and follow the CSS comment inside.

What you are building (9 sections):
1. Base/reset — box-sizing, font, dark background (`#0f1117`)
2. Auth screen — centered card layout
3. Header — app name + user info right-aligned
4. Drop zone — dashed border, highlight on drag-over, pulse animation on active upload
5. Progress bar — for upload progress display
6. File cards — grid layout, status badge colors (yellow/blue/green/red)
7. Results modal — full-screen overlay with scrollable content
8. Toasts — bottom-right stacked notifications, fade in/out
9. Utilities — `.hidden`, responsive breakpoints

### Step 6.3 — frontend/app.js

Open the file and follow the JS comment inside.

What you are building (5 sections):

**Section 1 — Auth / PKCE flow**
- On load: check URL for `?code=` (Cognito callback) → exchange code for tokens
- Store `code_verifier` in `sessionStorage` (NOT localStorage — PKCE security requirement)
- Store tokens in memory (JavaScript variables) — NEVER in localStorage (XSS risk)
- `login()` → redirect to Cognito Hosted UI with PKCE parameters
- `logout()` → clear in-memory tokens, redirect to Cognito logout endpoint

**Section 2 — API calls**
- `apiRequest(method, path, body)` — adds `Authorization: Bearer {accessToken}` header
- `getUploadUrl(fileName, contentType, fileSize)`
- `uploadFile(presignedUrl, file)` — PUT directly to S3 (not through the API)
- `listFiles(lastKey)`
- `getFileResults(fileId)`
- `deleteFile(fileId)`

**Section 3 — WebSocket**
- `connectWebSocket(userId)` — opens `WS_URL?userId={userId}`
- On message: parse JSON, find matching file card, update status badge
- Reconnect on close (exponential backoff, max 30s)

**Section 4 — UI rendering**
- `renderFileList(files)` — creates file cards from data
- `renderResultsModal(file)` — populates modal with summary/extracted text/labels
- `showToast(message, type)` — shows temporary notification

**Section 5 — Event listeners**
- DOMContentLoaded: check auth state → load files or show login
- Drop zone: dragover, dragleave, drop events
- Upload button: validate file → get presigned URL → PUT to S3 → poll status
- File card click: open results modal
- Delete button: confirm → call deleteFile → re-render list

---

## Phase 7 — Deploy

### Step 7.1 — Bootstrap CDK (first deploy only)

```bash
cdk bootstrap aws://<ACCOUNT-ID>/<REGION>
```

### Step 7.2 — Deploy in Order

```bash
cdk deploy SfiAuthStack
cdk deploy SfiStorageStack
cdk deploy SfiApiStack
cdk deploy SfiProcessingStack
cdk deploy SfiMonitoringStack
```

Or deploy all at once (respects add_dependency order):
```bash
cdk deploy --all
```

Note the outputs from each stack — you will need the API URL and WebSocket URL for the frontend.

### Step 7.3 — Configure Frontend

Update `frontend/app.js` with the deployed values from CDK outputs:
- `API_URL` — from SfiApiStack output
- `WS_URL` — from SfiApiStack output
- `COGNITO_DOMAIN` — from SfiAuthStack output
- `CLIENT_ID` — from SfiAuthStack output
- `REDIRECT_URI` — your CloudFront URL from SfiStorageStack output

### Step 7.4 — Deploy Frontend to S3

```bash
aws s3 sync frontend/ s3://<FRONTEND-BUCKET-NAME>/ --delete
```

The CloudFront distribution serves the frontend. Note: CloudFront has a cache TTL — after
uploading new files, create an invalidation:
```bash
aws cloudfront create-invalidation --distribution-id <DIST-ID> --paths "/*"
```

---

## Phase 8 — Integration Tests

### Step 8.1 — Create a Test User in Cognito

```bash
aws cognito-idp admin-create-user \
    --user-pool-id <USER-POOL-ID> \
    --username test@example.com \
    --temporary-password Temp1234!

aws cognito-idp admin-set-user-password \
    --user-pool-id <USER-POOL-ID> \
    --username test@example.com \
    --password YourTestPassword123! \
    --permanent
```

### Step 8.2 — tests/integration/test_pipeline.py

Open the file and follow the instructions inside.

What you are building:
- `auth_token` fixture — authenticates against real Cognito using `USER_PASSWORD_AUTH`
- `api` fixture — requests session with base URL and Authorization header
- `wait_for_status()` helper — polls GET /files/{fileId} until status matches or timeout
- `test_full_pdf_pipeline` — create minimal PDF in-memory → upload → poll → assert PROCESSED
- `test_full_image_pipeline` — same with JPEG
- `test_list_shows_uploaded_file`
- `test_delete_removes_file`
- `test_unauthorized_access_rejected`

Set environment variables and run:
```bash
export API_URL="https://<your-api-id>.execute-api.us-east-1.amazonaws.com/dev"
export WS_URL="wss://<your-ws-id>.execute-api.us-east-1.amazonaws.com/dev"
export TEST_EMAIL="test@example.com"
export TEST_PASSWORD="YourTestPassword123!"
pytest tests/integration/ -v --timeout=120
```

---

## Phase 9 — CI/CD (Optional but Recommended)

The `.github/workflows/deploy.yml` file should implement:

1. **On pull request**: `terraform plan` + `cdk synth` (validate only, no deploy)
2. **On push to main**: `terraform apply` → `cdk deploy --all`

Authentication: Use GitHub Actions OIDC (no static AWS keys). The IAM role for OIDC needs
`sts:AssumeRoleWithWebIdentity` permission and trusts `token.actions.githubusercontent.com`.

Key environment variable to set in GitHub Secrets:
- `AWS_ACCOUNT_ID`
- `AWS_REGION`
- `TF_VAR_account_id` (same as AWS_ACCOUNT_ID)
- `TF_VAR_environment` (e.g., `prod`)

---

## Recommended Build Order Summary

| Order | File | Phase |
|-------|------|-------|
| 1 | terraform/versions.tf | 1 |
| 2 | terraform/variables.tf | 1 |
| 3 | terraform/kms.tf | 1 |
| 4 | terraform/iam.tf | 1 |
| 5 | terraform/s3.tf | 1 |
| 6 | terraform/waf.tf | 1 |
| 7 | terraform/outputs.tf | 1 |
| 8 | **terraform apply** | 1 |
| 9 | backend/layers/shared/python/error_types.py | 2 |
| 10 | backend/layers/shared/python/response_helpers.py | 2 |
| 11 | backend/layers/shared/python/dynamo_client.py | 2 |
| 12 | backend/functions/get_upload_url/handler.py | 3 |
| 13 | backend/functions/list_files/handler.py | 3 |
| 14 | backend/functions/get_file_results/handler.py | 3 |
| 15 | backend/functions/delete_file/handler.py | 3 |
| 16 | backend/functions/process_document/handler.py | 3 |
| 17 | backend/functions/process_image/handler.py | 3 |
| 18 | backend/functions/ai_summarize/handler.py | 3 |
| 19 | backend/functions/websocket_handler/handler.py | 3 |
| 20 | backend/functions/housekeeping/handler.py | 3 |
| 21 | tests/unit/test_handlers.py | 4 |
| 22 | **pytest tests/unit/ -v** | 4 |
| 23 | infrastructure/stacks/auth_stack.py | 5 |
| 24 | infrastructure/stacks/storage_stack.py | 5 |
| 25 | infrastructure/stacks/api_stack.py | 5 |
| 26 | infrastructure/stacks/processing_stack.py | 5 |
| 27 | infrastructure/stacks/monitoring_stack.py | 5 |
| 28 | infrastructure/app.py | 5 |
| 29 | **cdk synth** | 5 |
| 30 | frontend/index.html | 6 |
| 31 | frontend/styles.css | 6 |
| 32 | frontend/app.js | 6 |
| 33 | **cdk deploy --all** | 7 |
| 34 | tests/integration/test_pipeline.py | 8 |
| 35 | **pytest tests/integration/ -v** | 8 |
