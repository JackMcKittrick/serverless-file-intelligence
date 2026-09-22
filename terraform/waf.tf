# terraform/waf.tf
# ==================
# WAF v2 WebACL attached to CloudFront.
#
# CRITICAL CONSTRAINT: CloudFront WAF WebACLs MUST live in us-east-1.
# All resources in this file use the `aws.us_east_1` provider alias defined
# in versions.tf — NOT the default provider. If you forget the alias, Terraform
# will attempt to create the WebACL in your default region and AWS will reject it.
#
# WHAT TO BUILD:
#
# ── RESOURCE 1: aws_wafv2_web_acl "main" ─────────────────────────────────────
#   resource "aws_wafv2_web_acl" "main" {
#     provider    = aws.us_east_1            ← REQUIRED — CloudFront WAF is us-east-1 only
#     name        = "${local.name_prefix}-waf"
#     description = "WAF for SFI CloudFront distribution"
#     scope       = "CLOUDFRONT"             ← Must be CLOUDFRONT (not REGIONAL)
#
#     default_action {
#       allow {}    ← allow traffic by default; rules below BLOCK specific bad traffic
#     }
#
#     # ── RULE 1: AWS Managed Core Rule Set ────────────────────────────────
#     rule {
#       name     = "AWSManagedRulesCommonRuleSet"
#       priority = 1
#       override_action { none {} }    ← use the rule group's own actions
#       statement {
#         managed_rule_group_statement {
#           name        = "AWSManagedRulesCommonRuleSet"
#           vendor_name = "AWS"
#         }
#       }
#       visibility_config {
#         cloudwatch_metrics_enabled = true
#         metric_name                = "${local.name_prefix}-common-rules"
#         sampled_requests_enabled   = true
#       }
#     }
#
#     # ── RULE 2: AWS Known Bad Inputs Rule Set ─────────────────────────────
#     rule {
#       name     = "AWSManagedRulesKnownBadInputsRuleSet"
#       priority = 2
#       override_action { none {} }
#       statement {
#         managed_rule_group_statement {
#           name        = "AWSManagedRulesKnownBadInputsRuleSet"
#           vendor_name = "AWS"
#         }
#       }
#       visibility_config {
#         cloudwatch_metrics_enabled = true
#         metric_name                = "${local.name_prefix}-bad-inputs"
#         sampled_requests_enabled   = true
#       }
#     }
#
#     # ── RULE 3: Rate Limiting ────────────────────────────────────────────
#     rule {
#       name     = "RateLimitRule"
#       priority = 3
#       action { block {} }    ← block (not count) when rate exceeded
#       statement {
#         rate_based_statement {
#           limit              = 1000    ← requests per 5 minutes per IP
#           aggregate_key_type = "IP"
#         }
#       }
#       visibility_config {
#         cloudwatch_metrics_enabled = true
#         metric_name                = "${local.name_prefix}-rate-limit"
#         sampled_requests_enabled   = true
#       }
#     }
#
#     visibility_config {
#       cloudwatch_metrics_enabled = true
#       metric_name                = "${local.name_prefix}-waf"
#       sampled_requests_enabled   = true
#     }
#   }
#
#   WHY THREE RULES:
#     Common Rule Set — blocks OWASP Top 10 (SQLi, XSS, LFI, RFI, etc.)
#     Known Bad Inputs — blocks log4shell, Spring4Shell, SSRF probes
#     Rate Limiting — prevents brute force; 1000 req/5min ≈ 3.3 req/sec per IP
#
# ── RESOURCE 2: aws_ssm_parameter "waf_web_acl_arn" ─────────────────────────
#   resource "aws_ssm_parameter" "waf_web_acl_arn" {
#     provider = aws.us_east_1    ← Store the SSM parameter in us-east-1 too,
#                                    so the CDK lookup reads from the same region
#     name  = "/sfi/${local.env}/waf-web-acl-arn"
#     type  = "String"
#     value = aws_wafv2_web_acl.main.arn
#   }
#   WHY: CDK StorageStack reads this at synth time and passes it to the
#        CloudFront distribution's web_acl_id property. CloudFront only accepts
#        the ARN (not the ID) for WAF associations.
#
# ── NOTE ON PROVIDER ALIAS ────────────────────────────────────────────────────
#   Both resources in this file use `provider = aws.us_east_1`.
#   This alias is declared in versions.tf:
#     provider "aws" {
#       alias  = "us_east_1"
#       region = "us-east-1"
#     }
#   Do NOT change the provider on either resource — AWS will reject CLOUDFRONT-scope
#   WAF creation outside us-east-1 with an error like:
#   "Error: scope is not REGIONAL, but the resource is not in us-east-1"

# TODO: implement the aws_wafv2_web_acl and aws_ssm_parameter resources above
