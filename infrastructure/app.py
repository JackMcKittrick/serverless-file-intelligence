import os

import aws_cdk as cdk

from stacks.auth_stack import AuthStack
from stacks.storage_stack import StorageStack
from stacks.api_stack import ApiStack
from stacks.processing_stack import ProcessingStack
from stacks.monitoring_stack import MonitoringStack

# this file is entry point for aws cdk application
# it creates 5 stacks connects their resources defines deployment dependencies adds tags
# and most imporantly generates cloudformation templates

# creates a CDK App object
# cdk.app is the root container for stacks
# and gives access to CDK context settings
app = cdk.App()

# two methods of getting aws account ID
account = os.environ.get("AWS_ACCOUNT_ID") or app.node.try_get_context("account")
if not account:
    raise ValueError("Set AWS_ACCOUNT_ID or provide CDK context 'account'.")

# read aws region
region = (
    os.environ.get("AWS_REGION")
    or app.node.try_get_context("region")
    or "us-east-1"
)
# read aws enviroment
environment = (
    os.environ.get("ENVIRONMENT")
    or app.node.try_get_context("environment")
    or "dev"
)

# creates a CDK enviroment object contaning the accoutn and region
env = cdk.Environment(account=account, region=region)

# create all 5 stacks below in the aws region and account in enviroment 
auth_stack = AuthStack(
    app,
    f"SFI-AuthStack-{environment}",
    environment=environment,
    env=env,
)

storage_stack = StorageStack(
    app,
    f"SFI-StorageStack-{environment}",
    environment=environment,
    env=env,
)
storage_stack.add_dependency(auth_stack)

api_stack = ApiStack(
    app,
    f"SFI-ApiStack-{environment}",
    environment=environment,
    user_pool=auth_stack.user_pool,
    user_pool_client=auth_stack.user_pool_client,
    uploads_bucket=storage_stack.uploads_bucket,
    files_table=storage_stack.files_table,
    uploads_kms_key=storage_stack.uploads_kms_key,
    env=env,
)
api_stack.add_dependency(auth_stack)
api_stack.add_dependency(storage_stack)

processing_stack = ProcessingStack(
    app,
    f"SFI-ProcessingStack-{environment}",
    environment=environment,
    uploads_bucket=storage_stack.uploads_bucket,
    processed_bucket=storage_stack.processed_bucket,
    files_table=storage_stack.files_table,
    env=env,
)
processing_stack.add_dependency(storage_stack)

monitoring_stack = MonitoringStack(
    app,
    f"SFI-MonitoringStack-{environment}",
    environment=environment,
    api_stack=api_stack,
    processing_stack=processing_stack,
    env=env,
)

# requires the API stack to deploy before monitorign stack 
monitoring_stack.add_dependency(api_stack)
# processing stack to deploy before monitoring
monitoring_stack.add_dependency(processing_stack)

# cdk.Tags is CDKs tagging helper
# gets tag manager and adds tags below onto the rout contruct aka app
# these tags are inherited by child constructs unless overriden
cdk.Tags.of(app).add("Project", "sfi")
cdk.Tags.of(app).add("Environment", environment)
cdk.Tags.of(app).add("ManagedBy", "CDK")

# CDK converts the stack definitions into a cloud assembly containing cloudformation templates and eployement meta data
# it generates deployment artifacts does not deploy the infrastructure need cd deploy --all for that 
app.synth()
