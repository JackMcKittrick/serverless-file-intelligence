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
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_kms as kms
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class ApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        uploads_bucket: s3.IBucket,
        files_table: dynamodb.Table,
        uploads_kms_key: kms.IKey,
        processed_bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # gets lambda role arn from ssm
        role_arn = ssm.StringParameter.value_from_lookup(
            self,
            f"/sfi/{environment}/lambda-execution-role-arn",
        )

        # if CDK receives a non valid ARN starting with this then synth can fail
        # so this is a commom preventor of that
        if role_arn.startswith("dummy-value-for-"):
            role_arn = (
                f"arn:{self.partition}:iam::{self.account}:"
                f"role/sfi-lambda-execution-{environment}"
            )

        # imports a referenc eot the existing role i created in terraform
        lambda_role = iam.Role.from_role_arn(
            self,
            "LambdaRole",
            role_arn,
        )

        # this creates a lambda layer
        # a layer is a shared folder of code/libraries that multiple lambda functions can use
        shared_layer = lambda_.LayerVersion(
            self,
            "SharedLayer",
            # this packages that local directory as the layers contents 
            # python layer dependencies in the path below not hte lamdba handler code
            code=lambda_.Code.from_asset("backend/layers/shared"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            compatible_architectures=[lambda_.Architecture.ARM_64],
            layer_version_name=f"sfi-shared-{environment}",
        )

        # a nested function can use variables from __init__ without you passing them in 
        # so inside here for convenience 
        # creates and returns a configured lambda function
        def make_function(
            name: str,  
            handler_path: str,  
            env_vars: dict[str, str] | None = None, 
        ) -> lambda_.Function:
            return lambda_.Function(
                self,
                name,  # construct ID
                function_name=f"sfi-{name.replace('_', '-')}-{environment}", # actual lamdba resource in aws
                runtime=lambda_.Runtime.PYTHON_3_11,
                architecture=lambda_.Architecture.ARM_64,
                code=lambda_.Code.from_asset(handler_path),
                handler="handler.handler",  # tells lambda to call the function named handler inside handler.py
                role=lambda_role,  # assigns imported execuatino role
                layers=[shared_layer],  # attaches shared layer
                environment={  # supplies enviroment variables
                    "TABLE_NAME": files_table.table_name,
                    "UPLOADS_BUCKET": uploads_bucket.bucket_name,
                    "PROCESSED_BUCKET": processed_bucket.bucket_name,
                    **(env_vars or {}),
                },  
                tracing=lambda_.Tracing.ACTIVE,  # enables active aws x ray tracing
                # x rya is debugging and mointoring service
                # tracks API gateway lambda dynamodb s3 and can where time spent
                timeout=Duration.seconds(30),   # max execution time
                memory_size=256, # allocates memory and cpu allocation scales with memory
            )

        # 5 below all use helper above to make lambda function and point to a lambda handler
        get_upload_url_fn = make_function(
            "get_upload_url",
            "backend/functions/get_upload_url",
        )
        list_files_fn = make_function(
            "list_files",
            "backend/functions/list_files",
        )
        get_file_results_fn = make_function(
            "get_file_results",
            "backend/functions/get_file_results",
        )
        delete_file_fn = make_function(
            "delete_file",
            "backend/functions/delete_file",
        )
        websocket_handler_fn = make_function(
            "websocket_handler",
            "backend/functions/websocket_handler",
        )

        # remember apigw is just a alias
        # this creates an API gaeway  REST API and stores its reference on stack
        self._api = apigw.RestApi(
            self,
            "RestApi",
            rest_api_name=f"sfi-api-{environment}",
            # a stage in API gaeway is deployed version of API
            deploy_options=apigw.StageOptions(
                stage_name=environment,
                tracing_enabled=True,  # enables x ray tracing for that stage
            ),
            # adds default broswer CORS preflight repsonses 
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            ),
        )
        # creates an authorizer that validates tokens issued by supplied congito user pool
        # like a security guard in front of api without anyone can call endpoint
        # with api gateway first checks does request include a token and was it issued valid by my cognito user pool
        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "Auth",
            cognito_user_pools=[user_pool],
        )

        # store cognito authentication settings once and reuse them for all protected API routes
        method_options = {
            "authorization_type": apigw.AuthorizationType.COGNITO, # this endpt requies cognito authentication
            "authorizer": cognito_authorizer,  # use this specific cognito authorizer to validate
        }

        # creates /files underneath the API root
        files = self._api.root.add_resource("files")
        # creates /files/upload
        upload = files.add_resource("upload")
        # creates /files/{fileId}
        file_item = files.add_resource("{fileId}")

        # connects a http route to a lambda
        # and apply authorizer to each API gateway path
        upload.add_method(
            "POST",
            apigw.LambdaIntegration(get_upload_url_fn),
            **method_options,
        )
        files.add_method(
            "GET",
            apigw.LambdaIntegration(list_files_fn),
            **method_options,
        )
        file_item.add_method(
            "GET",
            apigw.LambdaIntegration(get_file_results_fn),
            **method_options,
        )
        file_item.add_method(
            "DELETE",
            apigw.LambdaIntegration(delete_file_fn),
            **method_options,
        )

        # creates websocket API definition 
        self._websocket_api = apigwv2.WebSocketApi(
            self,
            "WebSocketApi",
            # assigns lambda to connect and disconnect route 
            api_name=f"sfi-ws-{environment}",  
            connect_route_options=apigwv2.WebSocketRouteOptions(
                integration=integrations.WebSocketLambdaIntegration(
                    "ConnectIntegration",
                    websocket_handler_fn,
                ),
            ),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(
                integration=integrations.WebSocketLambdaIntegration(
                    "DisconnectIntegration",
                    websocket_handler_fn,
                ),
            ),
        )

        # creates a deployed stage for websocket api
        # websockets different for example dynamodb table is single resource so it needs one cdk construct
        # but websocket is made up of multiple aws resources
        # the API itself like $connect and $disconnect then also at least one stage that makes API assesible thru URL
        websocket_stage = apigwv2.WebSocketStage(
            self,
            "WebSocketStage",
            web_socket_api=self._websocket_api,
            stage_name=environment,
            auto_deploy=True, # auto delpoys API changes to this stage
        )
        # grants lambda handler permission to manage this APIs connections including sending messages thru post_to_connection
        self._websocket_api.grant_manage_connections(websocket_handler_fn)

        # clients connect using the stages wss:// URL
        # frontend connects to this when app needs live processing updates after ifle uploaded
        # URL comes from AWS API gateway when you deploy it
        # this code copies that URL into a lambda settign
        websocket_handler_fn.add_environment(
            "WEBSOCKET_ENDPOINT",
            websocket_stage.callback_url,  # CDK gives acces to stages URL thru this
        )

        # tells aws when records change in the files table run websocket handler
        # previously we attached lambdas to a API 
        # here we attach event to the lambda so its invoked on event 
        websocket_handler_fn.add_event_source(
            event_sources.DynamoEventSource(
                files_table,  # use the stream attached to the table as trigger source
                starting_position=lambda_.StartingPosition.LATEST,  # start with newest changes
                batch_size=10,  # send up to 10 change records in one invocation
                bisect_batch_on_error=True,  # if processing batch fails split and retry
                retry_attempts=3,  
            ),
        )

        CfnOutput(self, "ApiUrl", value=self._api.url)
        CfnOutput(self, "WebSocketUrl", value=websocket_stage.url)

    @property
    def api(self) -> apigw.RestApi:
        return self._api

    @property
    def rest_api(self) -> apigw.RestApi:
        return self._api

    @property
    def websocket_api(self) -> apigwv2.WebSocketApi:
        return self._websocket_api