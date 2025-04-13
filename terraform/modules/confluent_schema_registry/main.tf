terraform {
  required_providers {
    confluent = {
      source  = "confluentinc/confluent"
      version = "~> 1.0"
    }
  }
}

# Create the Avro schema for the policy data
resource "confluent_schema" "policy_schema" {
  schema_registry_cluster {
    id = var.schema_registry_id
  }
  
  rest_endpoint = var.schema_registry_rest_endpoint
  
  subject_name = "${var.policy_topic_name}-value"
  format       = "AVRO"
  schema       = file("${var.schema_path}")
  
  credentials {
    key    = var.schema_registry_api_key_id
    secret = var.schema_registry_api_key_secret
  }
} 