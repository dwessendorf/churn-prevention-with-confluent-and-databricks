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
  default     = "us-east-1" # Change based on your region requirements
}

variable "apikey_owner_id" {
  description = "API key owner ID"
  type        = string
} 