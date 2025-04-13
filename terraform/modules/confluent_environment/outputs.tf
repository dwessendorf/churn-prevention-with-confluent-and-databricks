output "environment_id" {
  description = "ID of the created Confluent environment"
  value       = confluent_environment.main.id
}

output "schema_registry_id" {
  description = "ID of the created Schema Registry"
  value       = confluent_schema_registry_cluster.essentials.id
}

output "schema_registry_rest_endpoint" {
  description = "REST endpoint of the Schema Registry"
  value       = confluent_schema_registry_cluster.essentials.rest_endpoint
}

output "service_account_id" {
  description = "ID of the service account used for Schema Registry"
  value       = confluent_service_account.env_manager.id
}

output "schema_registry_api_key_id" {
  description = "API Key ID for Schema Registry"
  value       = confluent_api_key.schema_registry_api_key.id
  sensitive   = true
}

output "schema_registry_api_key_secret" {
  description = "API Key Secret for Schema Registry"
  value       = confluent_api_key.schema_registry_api_key.secret
  sensitive   = true
} 