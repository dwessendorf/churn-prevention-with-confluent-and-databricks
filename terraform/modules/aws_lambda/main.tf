provider "aws" {
  region = var.region
}

# Generate a random suffix for unique resource naming
resource "random_id" "suffix" {
  byte_length = 4
}

# Create IAM role for Lambda function
resource "aws_iam_role" "lambda_role" {
  name = "${var.function_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Attach policies to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Create a policy for Bedrock access
resource "aws_iam_policy" "bedrock_policy" {
  name        = "${var.function_name}-bedrock-policy"
  description = "Policy for AWS Bedrock access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach Bedrock policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.bedrock_policy.arn
}

# Secret Manager policy
resource "aws_iam_policy" "secretsmanager_policy" {
  name        = "${var.function_name}-secretsmanager-policy"
  description = "Policy for AWS Secrets Manager access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Effect   = "Allow"
        Resource = aws_secretsmanager_secret.kafka_secret.arn
      }
    ]
  })
}

# Attach Secrets Manager policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_secretsmanager" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.secretsmanager_policy.arn
}

# Create a secret for Kafka credentials
resource "aws_secretsmanager_secret" "kafka_secret" {
  name                    = "${var.secret_name}-${random_id.suffix.hex}"
  recovery_window_in_days = 0  # Allow immediate deletion/recreation
}

# Store Kafka secret value
resource "aws_secretsmanager_secret_version" "kafka_secret_version" {
  secret_id     = aws_secretsmanager_secret.kafka_secret.id
  secret_string = var.kafka_api_key_secret
}

# Create Lambda function
resource "aws_lambda_function" "function" {
  function_name    = var.function_name
  filename         = "${var.source_dir}/deployment-package.zip"
  source_code_hash = filebase64sha256("${var.source_dir}/deployment-package.zip")
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.lambda_handler"
  runtime          = var.runtime
  timeout          = 530
  memory_size      = 512

  environment {
    variables = {
      KAFKA_API_KEY_ID        = var.kafka_api_key_id
      SECRET_NAME             = aws_secretsmanager_secret.kafka_secret.name
      KAFKA_BOOTSTRAP_SERVER  = var.kafka_bootstrap_server
      KAFKA_TOPIC_NAME        = var.kafka_topic_name
      MIN_RECORDS_PER_RUN     = var.min_reviews_per_run
      MAX_RECORDS_PER_RUN     = var.max_reviews_per_run
      SECONDS_BETWEEN_REVIEWS = var.seconds_between_reviews
      POLICY_PRODUCER_TOPIC   = var.policy_producer_topic_name
    }
  }
}

# Create CloudWatch Events Rule for scheduled execution
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.function_name}-schedule"
  description         = "Schedule for Lambda Function"
  schedule_expression = "rate(1 minute)"
}

# Attach Lambda as target to CloudWatch Events Rule
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "${var.function_name}-target"
  arn       = aws_lambda_function.function.arn
}

# Allow CloudWatch to invoke Lambda
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
} 