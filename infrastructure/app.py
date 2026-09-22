"""
infrastructure/app.py — CDK App Entry Point
============================================
DEPLOY ORDER:
  Phase 1 (Terraform): cd terraform && terraform apply
    → Creates IAM roles, KMS keys, S3 buckets, WAF WebACL
    → Writes all ARNs/names to SSM Parameter Store
    → Must finish BEFORE cdk deploy runs

  Phase 2 (CDK): cdk deploy --all
    → Reads from SSM (value_from_lookup caches in cdk.context.json)
    → Deploy order: Auth → Storage → Api → Processing → Monitoring

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Import the five stack classes
  from stacks.auth_stack       import AuthStack
  from stacks.storage_stack    import StorageStack
  from stacks.api_stack        import ApiStack
  from stacks.processing_stack import ProcessingStack
  from stacks.monitoring_stack import MonitoringStack

STEP 2 — Read environment from env vars
  account     = os.environ["AWS_ACCOUNT_ID"]
  region      = os.environ.get("AWS_REGION", "us-east-1")
  environment = os.environ.get("ENVIRONMENT", "dev")
  env = cdk.Environment(account=account, region=region)

STEP 3 — Instantiate cdk.App()

STEP 4 — AuthStack (no dependencies)
  auth_stack = AuthStack(app, f"SFI-AuthStack-{environment}", environment=environment, env=env)

STEP 5 — StorageStack (reads Terraform SSM params — run terraform apply first)
  storage_stack = StorageStack(app, f"SFI-StorageStack-{environment}", environment=environment, env=env)

STEP 6 — ApiStack (depends on auth + storage)
  api_stack = ApiStack(app, f"SFI-ApiStack-{environment}",
      environment=environment,
      user_pool=auth_stack.user_pool,
      user_pool_client=auth_stack.user_pool_client,
      uploads_bucket=storage_stack.uploads_bucket,
      files_table=storage_stack.files_table,
      uploads_kms_key=storage_stack.uploads_kms_key,
      env=env)
  api_stack.add_dependency(auth_stack)
  api_stack.add_dependency(storage_stack)

STEP 7 — ProcessingStack (depends on storage)
  processing_stack = ProcessingStack(app, f"SFI-ProcessingStack-{environment}",
      environment=environment,
      uploads_bucket=storage_stack.uploads_bucket,
      processed_bucket=storage_stack.processed_bucket,
      files_table=storage_stack.files_table,
      env=env)
  processing_stack.add_dependency(storage_stack)

STEP 8 — MonitoringStack (depends on api + processing)
  monitoring_stack = MonitoringStack(app, f"SFI-MonitoringStack-{environment}",
      environment=environment,
      api_stack=api_stack,
      processing_stack=processing_stack,
      env=env)
  monitoring_stack.add_dependency(api_stack)
  monitoring_stack.add_dependency(processing_stack)

STEP 9 — Apply tags and call app.synth()
  cdk.Tags.of(app).add("Project", "serverless-file-intelligence")
  cdk.Tags.of(app).add("Environment", environment)
  cdk.Tags.of(app).add("ManagedBy", "CDK")
  app.synth()
"""

import os
import aws_cdk as cdk

# TODO: implement Steps 1-9 described above
