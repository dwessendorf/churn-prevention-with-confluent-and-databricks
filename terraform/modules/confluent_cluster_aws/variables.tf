variable "cluster_name" {
  description = "Name of the Confluent Kafka cluster"
  type        = string
}

variable "region" {
  description = "AWS region for the Confluent Kafka cluster"
  type        = string
}

variable "topic_name" {
  description = "Name of the Kafka topic"
  type        = string
}

variable "environment_id" {
  description = "ID of the Confluent environment"
  type        = string
}

variable "apikey_owner_id" {
  description = "ID of the API key owner"
  type        = string
} 