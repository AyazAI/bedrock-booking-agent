# Reference only. Do not apply this file from the portfolio setup.
# `terraform apply` creates billable AWS resources. Nothing in CI runs it.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "image_identifier" {
  type        = string
  description = "ECR image URI, including the tag."
}

provider "aws" {
  region = var.aws_region
}

resource "aws_apprunner_service" "booking" {
  service_name = "booking-agent"

  source_configuration {
    auto_deployments_enabled = false
    image_repository {
      image_identifier      = var.image_identifier
      image_repository_type = "ECR"
      image_configuration {
        port = "8000"
        runtime_environment_variables = {
          LLM_PROVIDER   = "mock"
          VECTOR_BACKEND = "chroma"
          PORT           = "8000"
        }
      }
    }
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    healthy_threshold   = 1
    unhealthy_threshold = 3
    interval            = 10
    timeout             = 5
  }

  # 1024 CPU units = 1 vCPU, 2048 MB = 2 GB.
  # The pricing page also lists 0.25 vCPU / 0.5 GB. This image pulls Chroma,
  # so the reference size leaves more RAM. Measure before going smaller.
  instance_configuration {
    cpu    = "1024"
    memory = "2048"
  }
}
