output "customer_review_function_arn" {
  description = "ARN of the customer review Lambda function"
  value       = module.customer_review_creator_lambda.function_arn
}

output "policy_producer_function_arn" {
  description = "ARN of the policy producer Lambda function"
  value       = module.policy_producer_lambda.function_arn
}

output "aws_kafka_cluster_id" {
  description = "ID of the AWS Confluent Kafka cluster"
  value       = module.confluent_cluster_aws.cluster_id
}

output "aws_kafka_bootstrap_servers" {
  description = "Bootstrap servers for the AWS Confluent Kafka cluster"
  value       = module.confluent_cluster_aws.bootstrap_servers
}

output "aws_kafka_rest_endpoint" {
  description = "REST endpoint for the AWS Confluent Kafka cluster"
  value       = module.confluent_cluster_aws.rest_endpoint
} 