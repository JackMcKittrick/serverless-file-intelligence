# terraform/versions.tf
# ======================
# Pin provider versions and configure the remote state backend.

terraform {
    # learned that this requires terraform version on machine
    
    required_version = "~> 1.7"   

    # learned HCL is HashiCorp Configuration Language its basically the grammer
    # terraform .tf are writtin in HCL
    # so terraform is engine or program that reads the HCL

    # learned that terraform uses plugins called providers
    # as you change the provider you change which cloud services you can use
    # I should think of provider as the dictionary of resources terraform can use
    # if you had instructions for all the clouds thatd be enormous 
    # terraform reads the file, compares actual vs desired state, then plans changes
    
    required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }

    # now terraform will understand resources starting iwth aws_
  }

}

# I learned terraform {...} is a terraform configuation block
# it tells terraform settings about the project

provider "aws" {

    # this sets aws region terraform should use by default
    # learned var is a like a built in namespace for intput variables
    # gonna be defined in variables.tf
  region = var.aws_region

# learned about nested blocks being blocks inside another block
# this one auto puts tags on many aws resources
  default_tags {
    # as I know keys are key/value pairs so created below
    tags = {
      Project     = "sfi"
      # learned standard practice bc switch from dev to stagin etc
      Environment = var.environment  
      ManagedBy   = "Terraform"
    }
  }
}

# learned that provider "aws" configures the aws plugin
# its a terraform block type and terraform has many different types of these
# above is the default aws provider config


# below is similar to above but this for cloudfront WAF bc must be created there

provider "aws" {

    # learend that the alias line creates another aws provider config
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "sfi"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# learned that provider configs control which AWS account/region/context resources are created in

locals {
  env         = var.environment
  account_id  = var.account_id
  region      = var.aws_region
  name_prefix = "sfi-${var.environment}"

  # last line demonstrates best use, can avoid repeating yourself 
  # ${...} means put value from inside here into string
}

# ive learned local values are reusable shortcuts
# put here because variables.tf is kept for inputs
# locals should be thought of as computed shortcuts

# learned terrform init reads all .tf files in directory
# but it doesn't execute them in order like a script
# it builds one large config and intializes providers