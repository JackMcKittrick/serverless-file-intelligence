# terraform/iam.tf
# =================
# Four IAM roles for Lambda functions and Step Functions.

resource "aws_iam_role" "lambda_execution" {
  name = "${local.name_prefix}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "lambda.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })
}

# learned aws_iam_role is how to create role resource type
# so lambda_execution is the local terraform name
# but the name is the real name that appears in AWS IAM
# the assume_role_policy is important bc thats the trust policy which says who can use the role
# lambda can take on the role when function runs 

resource "aws_iam_role_policy" "lambda_execution" {
  name = "${local.name_prefix}-lambda-execution-policy"
  role = aws_iam_role.lambda_execution.id

    # this named lambda_execution and thats ok bc different resource types
    # the role= line is what what attaches this policy to the role above
    # actually an inline policy because policy is created on the role you aren't using attachment resource

    # jsonencode is what terraform uses to turn policies into JSON for aws
  policy = jsonencode({
    Version = "2012-10-17"

    # mulitple statements in a policy
    Statement = [
      {
        Effect = "Allow"

        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
        ]

        Resource = [
          "arn:aws:dynamodb:*:${local.account_id}:table/sfi-files-${local.env}",
          "arn:aws:dynamodb:*:${local.account_id}:table/sfi-files-${local.env}/index/*",
        ]
      },
      {
        Effect = "Allow"

        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]

        Resource = [
          "arn:aws:s3:::sfi-uploads-${local.env}-${local.account_id}/*",
          "arn:aws:s3:::sfi-processed-${local.env}-${local.account_id}/*",
        ]
      },
      {
        Effect = "Allow"

        Action = [
          "ssm:GetParameter",
        ]

        Resource = "arn:aws:ssm:*:${local.account_id}:parameter/sfi/${local.env}/*"
      },
      {
        Effect = "Allow"

        Action = [
          "execute-api:ManageConnections",
        ]

        Resource = "arn:aws:execute-api:*:${local.account_id}:*/*/@connections/*"
      },
      {
        Effect = "Allow"

        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]

        Resource = [
          aws_kms_key.uploads.arn,
          aws_kms_key.table.arn,
        ]
      },
      {
        Effect = "Allow"

        Action = [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
        ]

        Resource = [
            "arn:aws:logs:*:${local.account_id}:log-group:/aws/lambda/sfi-*",
            "arn:aws:logs:*:${local.account_id}:log-group:/aws/lambda/sfi-*:*",
        ]
        },
        # theres log groups and log streams some actions target one or the other
        # to avoid permission errors for something like putlogevents the second resource allows the streams inside the groups
      {
        Effect = "Allow"

        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
        ]

        Resource = "*"
      }
    ]
  })
}

# the policy above gives API lambdas permission to do normal app work like 
# use dynamoDB, S3, SSM, API gateway, KMS, cloudwatch logs, and x ray

resource "aws_iam_role" "processing_lambda" {
  name = "${local.name_prefix}-processing-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "lambda.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })
}

# another role trusted by Lambda but the policy for this one includes more

resource "aws_iam_role_policy" "processing_lambda" {
  name = "${local.name_prefix}-processing-lambda-policy"
  role = aws_iam_role.processing_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = concat(
      jsondecode(aws_iam_role_policy.lambda_execution.policy).Statement,
      [
        {
          Effect = "Allow"

          Action = [
            "textract:DetectDocumentText",
            "textract:AnalyzeDocument",
            "rekognition:DetectLabels",
            "rekognition:DetectText",
            "comprehend:DetectEntities",
            "comprehend:DetectKeyPhrases",
            "sns:Publish",
          ]

          Resource = "*"
        },
        {
          Effect = "Allow"

          Action = [
            "bedrock:InvokeModel",
          ]

          Resource = "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-*"
        }
      ]
    )
  })
}

# whats cool is the concat() line what that does is take all the permissions
# from the policy before and add more such as textract, rekognition, comprehend, sns, and bedrock
# useful for least privledge and maintainability 

resource "aws_iam_role" "step_functions" {
  name = "${local.name_prefix}-stepfunctions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "states.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })
}

# role that step functions can take on

resource "aws_iam_role_policy" "step_functions" {
  name = "${local.name_prefix}-stepfunctions-policy"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "lambda:InvokeFunction",
        ]

        Resource = "arn:aws:lambda:*:${local.account_id}:function:sfi-*"
      },
      {
        Effect = "Allow"

        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]

        Resource = "*"
      },
      {
        Effect = "Allow"

        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
        ]

        Resource = "*"
      }
    ]
  })
}

# the policy above for step functions allows lambda functions to be invoked 
# along with write logs and publish tracing data

resource "aws_iam_role" "scheduler" {
  name = "${local.name_prefix}-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "scheduler.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "${local.name_prefix}-scheduler-policy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "lambda:InvokeFunction",
        ]

        Resource = "arn:aws:lambda:*:${local.account_id}:function:sfi-housekeeping-${local.env}"
      }
    ]
  })
}

# good servurity for event bridge scheduler bc it can only trigger this specific lambda

# same as what was done in kms.tf
# not permission but just sotring ARNs in SSM for the CDK

resource "aws_ssm_parameter" "lambda_execution_role_arn" {
  name  = "/sfi/${local.env}/lambda-execution-role-arn"
  type  = "String"
  value = aws_iam_role.lambda_execution.arn
}

resource "aws_ssm_parameter" "processing_lambda_role_arn" {
  name  = "/sfi/${local.env}/processing-lambda-role-arn"
  type  = "String"
  value = aws_iam_role.processing_lambda.arn
}

resource "aws_ssm_parameter" "stepfunctions_role_arn" {
  name  = "/sfi/${local.env}/stepfunctions-role-arn"
  type  = "String"
  value = aws_iam_role.step_functions.arn
}

resource "aws_ssm_parameter" "scheduler_role_arn" {
  name  = "/sfi/${local.env}/scheduler-role-arn"
  type  = "String"
  value = aws_iam_role.scheduler.arn
}
