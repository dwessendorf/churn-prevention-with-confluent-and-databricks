variable "environment_name" {
  description = "Name of the Confluent environment"
  type        = string
  default     = "churn-prevention-env"
}

variable "apikey_owner_id" {
  description = "API key owner ID"
  type        = string
} 