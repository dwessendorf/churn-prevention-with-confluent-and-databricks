variable "environment_name" {
  description = "Name of the Confluent environment"
  type        = string
}

variable "environment_id" {
  description = "ID of the Confluent environment"
  type        = string
}

variable "schema_registry_id" {
  description = "ID of the Schema Registry"
  type        = string
}

variable "schema_registry_rest_endpoint" {
  description = "REST endpoint for the Schema Registry"
  type        = string
}

variable "policy_topic_name" {
  description = "Name of the policy topic"
  type        = string
}

variable "schema_path" {
  description = "Path to the schema file"
  type        = string
}

variable "schema_registry_api_key_id" {
  description = "API Key ID for Schema Registry"
  type        = string
  sensitive   = true
}

variable "schema_registry_api_key_secret" {
  description = "API Key Secret for Schema Registry"
  type        = string
  sensitive   = true
} 