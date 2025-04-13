output "function_arn" {
  description = "The ARN of the Lambda function"
  value       = aws_lambda_function.function.arn
}

output "function_name" {
  description = "The name of the Lambda function"
  value       = aws_lambda_function.function.function_name
}

output "role_arn" {
  description = "The ARN of the IAM role attached to the Lambda function"
  value       = aws_iam_role.lambda_role.arn
}

output "secret_arn" {
  description = "The ARN of the secret containing Kafka API key"
  value       = aws_secretsmanager_secret.kafka_secret.arn
} 