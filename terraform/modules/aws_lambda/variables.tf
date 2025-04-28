variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "region" {
  description = "AWS region to deploy to"
  type        = string
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

variable "kafka_topic_name" {
  description = "Kafka topic name"
  type        = string
}

variable "secret_name" {
  description = "Name of the secret to store Kafka API key"
  type        = string
}

variable "min_reviews_per_run" {
  description = "Minimum number of reviews to generate per run"
  type        = string
}

variable "max_reviews_per_run" {
  description = "Maximum number of reviews to generate per run"
  type        = string
}

variable "seconds_between_reviews" {
  description = "Seconds between review generation"
  type        = string
}

variable "source_dir" {
  description = "Directory containing the Lambda function source code"
  type        = string
}

variable "kafka_api_key_id" {
  description = "Kafka API key ID"
  type        = string
}

variable "kafka_api_key_secret" {
  description = "Kafka API key secret"
  type        = string
}

variable "kafka_bootstrap_server" {
  description = "Kafka bootstrap server"
  type        = string
}

variable "policy_producer_topic_name" {
  description = "Kafka topic name used by the policy producer (for the consumer to read from)"
  type        = string
  default     = ""
} 