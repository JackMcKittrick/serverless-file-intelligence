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
# imports 3 classes from aws cdk library 
# cfnOutput defines cloudformatino displays after deployement
# removalpolicy controls what happens to a resource when cloudformation removes it
#stack represents a collection of infrastructure managed as one CF stack
from aws_cdk import CfnOutput, RemovalPolicy, Stack
# the as lets you give shorter name
from aws_cdk import aws_cognito as cognito
# everything in CDK is a construct its the base class of all CDK resources and containers
from constructs import Construct

# AuthStack will inherit from CDK Stack class giving it behavior needed to prepresent a cloudformation stack
class AuthStack(Stack):
    # constructor
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        cloudfront_domain: str = "example.cloudfront.net",  # default value
        **kwargs,
    ) -> None:
        # super(). accesses the parent class behavior 
        # scope is the parent object that contains the stack
        # construct_id is the name for the stack construct
        super().__init__(scope, construct_id, **kwargs)

        # stores enviroment variable on the object
        self._environment = environment

        # app is the top level container
        # app contains Stacks
        # then a stack contains resources/constructs rememeber everything in CDK is a Construct
        # so app = cdk.App() creats an App construct and s3.Bucket(...) creates a bucket construct
        # this creates a CDK construct decribing a congnito user pool and stores it on the stack
        # remember this class is creating a stack so thats the stack its assigned to
        self._user_pool = cognito.UserPool(
            self,   # if outside the stack class going to pass in stack variable
            # inside the stack class its the stack variable itself
            "UserPool",  # within the stack UserPool is the ID for this cognito construct
            user_pool_name=f"sfi-users-{environment}",  # this is the actual congnito user pool name in aws
            self_sign_up_enabled=True,  # allows users to register their own accounts
            sign_in_aliases=cognito.SignInAliases(email=True),  # email is a sign in identifier
            auto_verify=cognito.AutoVerifiedAttrs(email=True),   # configs cognito to auto initiate email verification during sign up
            # strong password requirements
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            # normally if you do cdk destory you delete stack then delete user pool then delete all users
            # with this retain itll delete the stack but leave the user pool alone in aws account
            removal_policy=RemovalPolicy.RETAIN,
        )
        # so i created the user pool wiht users password policy and sign in setting
        # now my frontend needs permission to use that user pool so we make a user pool client
        # an app client identifies an application allowed to auth users thru its pool
        self._user_pool_client = self._user_pool.add_client(
            "WebClient",   # wihtin the user pool created above this gets contrust ID webclient
            user_pool_client_name=f"sfi-web-client-{environment}",   # name ill see in congito/aws 
            generate_secret=False,   
            # when user clicks login front end redirects them to cognito 
            # the frontend still provides client ID but theres no secret bc any secret shipped to the broswer is visible to the user
            auth_flows=cognito.AuthFlow(
                user_password=True,   # allow cognitos username/password auth flow
                user_srp=True,  # allows secure remote password auth
                # SRP uses a cryptographic exchange to prove knowledge of the password without sending password itself
            ),
            # remember OAuth is an open-standard industry protocol that lets websites access your data on another service like Google without ever seeing or storing your password
            # in my app the frontend is the OAuth client and cognito is the Auth server
            # starts config for browswer based sign in and redirects
            o_auth=cognito.OAuthSettings(
                # flow means which OAuth login processes is this app client allowed to use
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True, # modern and recommended 
                    # broswer to cognito login the user signs in then cognito sends back auth code (not progrmaming code) which frontend exchanges for tokens
                    # then get access tokens
                    implicit_code_grant=False,  # older approach was broswer then login then tokens returned immdediately
                ),
                # when your frontend logs into Cognito it asks for certain scopes
                scopes=[
                    cognito.OAuthScope.OPENID,  # tells cognito I want to identify who user is
                    # lets cognito issue an ID token containing identify info 
                    cognito.OAuthScope.EMAIL, # access to users email information
                    cognito.OAuthScope.PROFILE, # access to basic profile information
                ],
                # after login or logout where to send the users broswer
                # cognito only allows redirects to URLs youve registered
                callback_urls=[f"https://{cloudfront_domain}/callback"],  # cognito redirects broswer here and sends auth code as well
                logout_urls=[f"https://{cloudfront_domain}/"],  # cognito sends after logout
            ),
            prevent_user_existence_errors=True,   # stops users from figuring out a users email exists
        )
        # for congito the hosted UI is the actual website AWS for you
        # aws needs a domain so users can reach those pages
        # this below tells congito create a web address for my login pages
        domain = self._user_pool.add_domain(
            "Domain",  
            # this is a AWS managed congito domain and builds the domain prefix
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"sfi-{environment}-{self.account}",
            ),
        )

        # these below are after cloudformatino creates the stack print these values 
        CfnOutput(
            self,
            "UserPoolId",
            value=self._user_pool.user_pool_id,
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=self._user_pool_client.user_pool_client_id,
        )

        CfnOutput(
            self,
            "HostedUiUrl",
            value=domain.base_url(),
        )

    # @property is a decorator that maeks following method accessible as an attribute
    # its basically like let me call a function as if were a variable
    # an attribute is something accessed with a dot like person.name then name is an attribute
    # without @property id have to call a method like person.get_name()
    # defines getter with a nice public name as user_pool and returns the user pool construct
    @property
    def user_pool(self) -> cognito.UserPool:
        return self._user_pool

    @property
    def user_pool_client(self) -> cognito.UserPoolClient:
        return self._user_pool_client