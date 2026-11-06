terraform {
  required_version = "~> 1.13.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.72.0"
    }
  }
  backend "local" {
    path = "../../.platform/tofu/terraform.tfstate"
  }
}

locals {
  endpoint = "http://127.0.0.1:14566"
  # S3 Control requests get the account ID prepended to the host
  # (000000000000.<host>). localhost.localstack.cloud has wildcard DNS to 127.0.0.1.
  s3control_endpoint = "http://localhost.localstack.cloud:14566"
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  allowed_account_ids         = ["000000000000"]
  s3_use_path_style           = true
  skip_metadata_api_check     = true
  skip_credentials_validation = true
  endpoints {
    sts = local.endpoint
    s3  = local.endpoint
    # Provider >= 6.23 reads and writes bucket tags via S3 Control. Without this
    # override those calls go to real AWS.
    s3control = local.s3control_endpoint
    iam       = local.endpoint
    sqs       = local.endpoint
    lambda    = local.endpoint
    dynamodb  = local.endpoint
    logs      = local.endpoint
  }
}

resource "aws_s3_bucket" "input" {
  bucket = "boutique-lab-input"
}
resource "aws_sqs_queue" "dead" {
  name = "boutique-dead"
}
resource "aws_sqs_queue" "work" {
  name                       = "boutique-work"
  visibility_timeout_seconds = 60
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead.arn
    maxReceiveCount     = 2
  })
}
resource "aws_sqs_queue_policy" "s3" {
  queue_url = aws_sqs_queue.work.url
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.work.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_s3_bucket.input.arn } }
    }]
  })
}
resource "aws_s3_bucket_notification" "imports" {
  bucket = aws_s3_bucket.input.id
  queue {
    queue_arn     = aws_sqs_queue.work.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "imports/"
    filter_suffix = ".csv"
  }
  depends_on = [aws_sqs_queue_policy.s3]
}
resource "aws_dynamodb_table" "results" {
  name         = "employeeInfoNew"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "name"
  attribute {
    name = "name"
    type = "S"
  }
}
resource "aws_iam_role" "worker" {
  name = "boutique-sample-worker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}
resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/boutique-sample-worker"
  retention_in_days = 3
}
resource "aws_iam_role_policy" "worker" {
  role = aws_iam_role.worker.id
  name = "process-imports"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.work.arn },
      { Effect = "Allow", Action = "s3:GetObject", Resource = "${aws_s3_bucket.input.arn}/imports/*" },
      { Effect = "Allow", Action = "dynamodb:PutItem", Resource = aws_dynamodb_table.results.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.worker.arn}:*" }
    ]
  })
}
resource "aws_lambda_function" "worker" {
  function_name    = "boutique-sample-worker"
  role             = aws_iam_role.worker.arn
  handler          = "index.lambda_handler"
  runtime          = "python3.12"
  timeout          = 10
  filename         = "${path.module}/../../.platform/tofu/worker.zip"
  source_code_hash = filebase64sha256("${path.module}/../../.platform/tofu/worker.zip")
  environment {
    variables = { AWS_ENDPOINT_URL = "http://boutique-aws-localstack:4566" }
  }
}
resource "aws_lambda_event_source_mapping" "work" {
  event_source_arn = aws_sqs_queue.work.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1
  depends_on       = [aws_iam_role_policy.worker]
}
