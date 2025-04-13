variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "runtime" {
  description = "Runtime for the Lambda function"
  type        = string
  default     = "python3.11"
}

variable "entry_point" {
  description = "Entry point for the Lambda function"
  type        = string
  default     = "main"
}

variable "customer_review_function_name" {
  description = "Name of the customer review Lambda function"
  type        = string
  default     = "customer-review-creator"
}

variable "policy_producer_function_name" {
  description = "Name of the policy producer Lambda function"
  type        = string
  default     = "policy-producer"
}

variable "customer_review_kafka_topic_name" {
  description = "Kafka topic name for customer reviews"
  type        = string
  default     = "customer-reviews"
}

variable "policy_producer_kafka_topic_name" {
  description = "Kafka topic name for policy producer"
  type        = string
  default     = "policy-producer"
}

variable "customer_review_secret_name" {
  description = "Name of the secret for customer review function"
  type        = string
  default     = "customer-review-kafka-secret"
}

variable "policy_producer_secret_name" {
  description = "Name of the secret for policy producer function"
  type        = string
  default     = "policy-producer-kafka-secret"
}

variable "customer_review_min_reviews_per_run" {
  description = "Minimum number of reviews to generate per run for customer review function"
  type        = string
  default     = "10"
}

variable "customer_review_max_reviews_per_run" {
  description = "Maximum number of reviews to generate per run for customer review function"
  type        = string
  default     = "20"
}

variable "customer_review_seconds_between_reviews" {
  description = "Seconds between review generation for customer review function"
  type        = string
  default     = "5"
}

variable "policy_producer_min_reviews_per_run" {
  description = "Minimum number of reviews to generate per run for policy producer function"
  type        = string
  default     = "10"
}

variable "policy_producer_max_reviews_per_run" {
  description = "Maximum number of reviews to generate per run for policy producer function"
  type        = string
  default     = "20"
}

variable "policy_producer_seconds_between_reviews" {
  description = "Seconds between review generation for policy producer function"
  type        = string
  default     = "5"
}

variable "aws_cluster_name" {
  description = "Name of the AWS Confluent cluster"
  type        = string
  default     = "aws-kafka-cluster"
}

variable "environment_name" {
  description = "Name of the Confluent environment"
  type        = string
  default     = "churn-prevention-env"
}

variable "schema_registry_package" {
  description = "Package type for Schema Registry (ESSENTIALS or ADVANCED)"
  type        = string
  default     = "ESSENTIALS"
}

variable "schema_registry_region" {
  description = "Region for Schema Registry deployment"
  type        = string
  default     = "us-east-1"
}

variable "apikey_owner_id" {
  description = "ID of the API key owner"
  type        = string
}

variable "confluent_cloud_api_key" {
  description = "Confluent Cloud API Key"
  type        = string
  sensitive   = true
}

variable "confluent_cloud_api_secret" {
  description = "Confluent Cloud API Secret"
  type        = string
  sensitive   = true
} 