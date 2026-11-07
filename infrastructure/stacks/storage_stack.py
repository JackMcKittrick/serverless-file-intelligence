from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct

# this class defines aws resources for apps storage and frontend deliver
# connects to terraform resources creates a dynamoDB table, s3 bucket, and cloudfront distribution for front end
# when CDK application instantiates this class its constructor builds a resource definition
# cdk synth will convert that definition into a cloudformation template
# delployment creates or configs the resources
class StorageStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        **kwargs,
    ) -> None:
        
        super().__init__(scope, construct_id, **kwargs)

        self._environment = environment

        # all above similiar to auth stack learned there
        # builds common SSM parameter path gonna be used to access terraform resources
        parameter_prefix = f"/sfi/{environment}"

        # all 5 of the variables used value_from_lookup() 
        # with that function call CDK tries to get the value during synth so its good when you need actual value at synth time
        # synth obviously short for synthesize is process of aws translating programming code here python into cloudformation templates
        # value_for_string_parameter returns a cloudformation token meaning actual value isnt needed during synth and value is resolved during deployement
        # going to switch to value_for_string_parameter because with value_from_lookup() the CDK uses a dumby value which is a temporary placeholder
        # but my code tries to use the placeholder as if it were a real bucket 
        # this is because the lookup is done after synthesis finishes 
        # they end up as string paths with name or arn 
        uploads_bucket_name = ssm.StringParameter.value_for_string_parameter(
            self, f"{parameter_prefix}/uploads-bucket-name"
        )
        processed_bucket_name = ssm.StringParameter.value_for_string_parameter(
            self, f"{parameter_prefix}/processed-bucket-name"
        )
        uploads_kms_key_arn = ssm.StringParameter.value_for_string_parameter(
            self, f"{parameter_prefix}/uploads-kms-key-arn"
        )
        table_kms_key_arn = ssm.StringParameter.value_for_string_parameter(
            self, f"{parameter_prefix}/table-kms-key-arn"
        )
        waf_web_acl_arn = ssm.StringParameter.value_for_string_parameter(
            self, f"{parameter_prefix}/waf-web-acl-arn"
        )

        # below 4 cases of importing existing aws resources into CDK not creating new ones
        # these resources were created by terraform
        # it takes the paths from above and gets a CDK object that represents it
        self._uploads_bucket = s3.Bucket.from_bucket_name(
            self, "UploadsBucket", uploads_bucket_name
        )
        self._processed_bucket = s3.Bucket.from_bucket_name(
            self, "ProcessedBucket", processed_bucket_name
        )

        self._uploads_kms_key = kms.Key.from_key_arn(
            self, "UploadsKMSKey", uploads_kms_key_arn
        )
        self._table_kms_key = kms.Key.from_key_arn(
            self, "TableKMSKey", table_kms_key_arn
        )

        # this configs existing uploads bucket to send events to eventbridge
        # this is the starting event for the processing workflow
        # bucket remains externally owned but this line still configs notification settings when deployed
        self._uploads_bucket.enable_event_bridge_notification()

        # this creates a dynamoDB table construct and stores it on the stack
        self._files_table = dynamodb.Table(
            self,
            "FilesTable",  # contruct ID in stack
            table_name=f"sfi-files-{environment}",  # physical aws table name
            # dynamoDB items only have one primary key
            # either partition key only or partition key + sort key which is a composite primary key
            # partition key determines which dynamoDB partition aka storage node stores the item
            # sort key organizes items within same partition key
            # because i specified both a PK and SK i am using a composite key
            # for just PK as primary key i would have to have no sort key
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, # on demand billing for reads and writes
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,  # selects encryptino using a customer managed KMS key
            # its a CMK because i created the resource in terraform with resource "aws_kms_key" "table" {
            encryption_key=self._table_kms_key,  # gives the imported key used for table encryption
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,  # enables dynamoDB streams with items before and after images
            time_to_live_attribute="ttl",  # names ttl as expiration attribute
            # items that use it must provide an expiration time as a Unix timestamp
            # deletion is asynchronous meaning dynamoDB doenst delete it at that second
            # theres a AWS managed background process that periodically looks for expired items and removes them
            removal_policy=RemovalPolicy.RETAIN,  # keeps table when deleted from stack
            point_in_time_recovery=True,   # enables point in time recovery which lets you resotre a dynamnoDB table how 
            # it looked at a specific moment in the past
        )

        # this adds a global secondary index to the table noto literally another table but prety close conceptually
        # this allows for another query access pattern 
        # data is copied so dynamoDB stores extra data for index
        # GSIs consume storage and write capacity
        # this is used for processing and pending queries
        self._files_table.add_global_secondary_index(
            index_name="StatusIndex",
            partition_key=dynamodb.Attribute(
                name="processingStatus",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="uploadedAt",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,  # copies all itme attributes into the index 
            # so queries can retrieve complete records directly front it
        )

        # another second index that groups entries by content type like image/png
        self._files_table.add_global_secondary_index(
            index_name="FileTypeIndex",
            partition_key=dynamodb.Attribute(
                name="contentType",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="uploadedAt",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
            # only stores the tables primary keys and the index keys so less attributes copied into the index
        )

        # this creates a new CDK managaed s3 bucket for the frontends 
        # HMTL JavaScript CSS and other assets
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,  # no public access to the bucket 
            # cloudfront will receive authorized access thru OAC
            # OAC is orgin access control so users don't access files directly from s3 its thru cloudfront
            # OAC tells s3 only this cloudfront distribution is allowed to read objects from this bucket
            encryption=s3.BucketEncryption.S3_MANAGED, # use s3 managed encryption 
            enforce_ssl=True, # must use ssl to communicate with bucket
            removal_policy=RemovalPolicy.DESTROY,   # cloudformation can delete the bucket when stack is destroyed
            auto_delete_objects=True, # cleanup to delete bucket objects during removal so bucket can be deleted
        )

        # this creates the OAC resource cloudfront uses to auth requests to s3
        # this alone isnt what tells s3 which cloudfront the request came from
        # this just creates config and tells cloudfront to sign requests
        origin_access_control = cloudfront.S3OriginAccessControl(
            self,
            "FrontendOriginAccessControl",
            signing=cloudfront.Signing.SIGV4_ALWAYS,
            # cloudfront always sign origin requests using AWs signature version 4
        )

        self._distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                # sets frontend bucket as the origin when cloudfront needs a file
                # also use this OAC when takign to the bucket
                # CDK will also generate the appropriate bucket policy so s3 trusts this cloudfront
                # done by CDK not me manually
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    frontend_bucket,
                    origin_access_control=origin_access_control,
                ),
                # if user visits with http then always end up on https
                viewer_protocol_policy=(
                    cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
                ),
                # cloudfront caches at the edge locations
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            web_acl_id=waf_web_acl_arn, # attaches a WAF 
            default_root_object="index.html",  # if someone visits cloudfront requests index.html
            # go to index.html if error
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_page_path="/index.html",
                    response_http_status=200,
                ),
            ],
        )

        CfnOutput(
            self,
            "FilesTableName",
            value=self._files_table.table_name,
        )
        CfnOutput(
            self,
            "FilesTableArn",
            value=self._files_table.table_arn,
        )
        CfnOutput(
            self,
            "CloudFrontUrl",
            value=f"https://{self._distribution.distribution_domain_name}",
        )
        CfnOutput(
            self,
            "FrontendBucketName",
            value=frontend_bucket.bucket_name,
        )

    @property
    def table(self) -> dynamodb.Table:
        return self._files_table

    @property
    def files_table(self) -> dynamodb.Table:
        return self._files_table

    @property
    def uploads_bucket(self) -> s3.IBucket:
        return self._uploads_bucket

    @property
    def processed_bucket(self) -> s3.IBucket:
        return self._processed_bucket

    @property
    def uploads_kms_key(self) -> kms.IKey:
        return self._uploads_kms_key

    @property
    def distribution(self) -> cloudfront.Distribution:
        return self._distribution