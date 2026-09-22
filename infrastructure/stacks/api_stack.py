"""
infrastructure/stacks/api_stack.py
====================================
CDK stack: REST API Gateway + Lambda functions + WebSocket API.

Constructor params (passed from app.py):
  user_pool, user_pool_client  ← from AuthStack
  uploads_bucket, files_table  ← from StorageStack
  uploads_kms_key              ← from StorageStack

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Read IAM role ARNs from SSM
  Lambda execution role ARN is at /sfi/{env}/lambda-execution-role-arn
  Use ssm.StringParameter.value_from_lookup() — the role was created by Terraform
  Import: iam.Role.from_role_arn(self, "LambdaRole", role_arn)

STEP 2 — Create the shared Lambda layer
  lambda_.LayerVersion with:
    code = lambda_.Code.from_asset("backend/layers/shared")
    compatible_runtimes = [lambda_.Runtime.PYTHON_3_11]
    layer_version_name = f"sfi-shared-{environment}"

STEP 3 — Helper function: make_function(name, handler_path, env_vars)
  Create a lambda_.Function with:
    runtime = PYTHON_3_11
    architecture = ARM_64   ← Graviton2, ~20% cheaper
    code = lambda_.Code.from_asset(handler_path)
    handler = "handler.handler"
    role = the imported execution role
    layers = [shared_layer]
    environment = env_vars + {"TABLE_NAME": files_table.table_name}
    tracing = lambda_.Tracing.ACTIVE   ← X-Ray
    timeout = Duration.seconds(30)
    memory_size = 256
  WHY: A helper avoids repeating these settings 9 times.

STEP 4 — Create the 7 REST API Lambda functions
  get_upload_url:  env = {UPLOADS_BUCKET: ..., TABLE_NAME: ...}
  list_files:      env = {TABLE_NAME: ...}
  get_file_results: env = {PROCESSED_BUCKET: ..., TABLE_NAME: ...}
  delete_file:     env = {UPLOADS_BUCKET: ..., PROCESSED_BUCKET: ..., TABLE_NAME: ...}
  (process_document, process_image, ai_summarize go in ProcessingStack)

STEP 5 — Create the REST API
  apigw.RestApi with:
    rest_api_name = f"sfi-api-{environment}"
    deploy_options = apigw.StageOptions(stage_name=environment, tracing_enabled=True)
    default_cors_preflight_options = CorsOptions(allow_origins=["*"])
  Add a Cognito authorizer:
    apigw.CognitoUserPoolsAuthorizer(self, "Auth", cognito_user_pools=[user_pool])
  Wire routes:
    GET  /files               → list_files_fn
    POST /files/upload        → get_upload_url_fn
    GET  /files/{fileId}      → get_file_results_fn
    DELETE /files/{fileId}    → delete_file_fn
  All methods: authorization_type=COGNITO, authorizer=cognito_authorizer

STEP 6 — Create the WebSocket API
  apigwv2.WebSocketApi with:
    api_name = f"sfi-ws-{environment}"
    connect_route_options    → websocket_handler_fn
    disconnect_route_options → websocket_handler_fn
  Create a WebSocketStage and deploy
  Grant the websocket Lambda permission to post_to_connection on the API

STEP 7 — Wire WebSocket handler's DynamoDB Stream trigger
  websocket_handler_fn.add_event_source(
      DynamoEventSource(files_table, starting_position=START_FROM_LATEST,
                        batch_size=10, bisect_on_function_error=True)
  )
  WHY: DynamoDB Streams trigger the WebSocket Lambda every time a file record
       changes status — this is how clients get real-time updates without polling.

STEP 8 — CfnOutputs + Python properties
  Outputs: ApiUrl, WebSocketUrl
  Properties: rest_api, websocket_api (for MonitoringStack to add alarms)
"""

from aws_cdk import Stack, Duration, CfnOutput
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_kms as kms
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class ApiStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 environment: str,
                 user_pool: cognito.UserPool,
                 user_pool_client: cognito.UserPoolClient,
                 uploads_bucket: s3.IBucket,
                 files_table: dynamodb.Table,
                 uploads_kms_key: kms.IKey,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # TODO: implement Steps 1-8 described above

    @property
    def rest_api(self) -> apigw.RestApi:
        raise NotImplementedError("Implement Step 5 first")
