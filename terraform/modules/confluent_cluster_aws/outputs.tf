output "cluster_id" {
  description = "ID of the Confluent Kafka cluster"
  value       = confluent_kafka_cluster.cluster.id
}

output "api_key_id" {
  description = "API key ID for the Confluent Kafka cluster"
  value       = confluent_api_key.kafka_api_key.id
}

output "api_key_secret" {
  description = "API key secret for the Confluent Kafka cluster"
  value       = confluent_api_key.kafka_api_key.secret
  sensitive   = true
}

output "bootstrap_servers" {
  description = "Bootstrap servers for the Confluent Kafka cluster"
  value       = confluent_kafka_cluster.cluster.bootstrap_endpoint
}

output "rest_endpoint" {
  description = "REST endpoint for the Confluent Kafka cluster"
  value       = confluent_kafka_cluster.cluster.rest_endpoint
} 