"""
infrastructure/stacks/auth_stack.py
=====================================
CDK stack: Cognito User Pool + App Client + Hosted UI.
Deploy this FIRST — every other stack that validates JWTs depends on the User Pool.

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Create the Cognito User Pool
  cognito.UserPool with:
    user_pool_name = f"sfi-users-{environment}"
    self_sign_up_enabled = True
    sign_in_aliases = cognito.SignInAliases(email=True)
    auto_verify = cognito.AutoVerifiedAttrs(email=True)
    password_policy — min 8 chars, require uppercase + number + symbol
    removal_policy = RemovalPolicy.RETAIN   ← NEVER destroy user accounts
  WHY: RETAIN means cdk destroy never deletes existing user data. Email-only
       sign-in is simpler than username+email for a portfolio project.

STEP 2 — Create an App Client
  user_pool.add_client("WebClient",
    user_pool_client_name = f"sfi-web-client-{environment}",
    auth_flows = cognito.AuthFlow(user_password=True, user_srp=True),
    o_auth = cognito.OAuthSettings(
        flows = cognito.OAuthFlows(authorization_code_grant=True),
        scopes = [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
        callback_urls = [f"https://{cloudfront_domain}/callback"],   ← placeholder for now
        logout_urls   = [f"https://{cloudfront_domain}/"],
    ),
    prevent_user_existence_errors = True,
  )
  WHY: PKCE authorization code grant (not implicit) is the secure OAuth 2.0 flow
       for SPAs — access tokens never appear in the URL.

STEP 3 — Create a Hosted UI domain
  user_pool.add_domain("Domain",
    cognito_domain = cognito.CognitoDomainOptions(
        domain_prefix = f"sfi-{environment}-{self.account}"
    )
  )
  WHY: The Cognito Hosted UI handles the login page for you — no need to build
       a custom login form or handle credentials in JavaScript.

STEP 4 — CfnOutputs
  Export: UserPoolId, UserPoolClientId, HostedUiUrl (for README)

STEP 5 — Python properties (for cross-stack passing in app.py)
  @property def user_pool(self) -> cognito.UserPool
  @property def user_pool_client(self) -> cognito.UserPoolClient
"""

from aws_cdk import RemovalPolicy, Stack, CfnOutput
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class AuthStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # TODO: implement Steps 1-5 described above

    @property
    def user_pool(self) -> cognito.UserPool:
        raise NotImplementedError("Implement Step 1 first")

    @property
    def user_pool_client(self) -> cognito.UserPoolClient:
        raise NotImplementedError("Implement Step 2 first")
