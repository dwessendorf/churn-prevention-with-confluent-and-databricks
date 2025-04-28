terraform {
  required_providers {
    confluent = {
      source  = "confluentinc/confluent"
      version = "2.25.0"
    }
  }
}

# Create a Confluent Environment
resource "confluent_environment" "main" {
  display_name = var.environment_name
}

# Create service account for environment management
resource "confluent_service_account" "env_manager" {
  display_name = "${var.environment_name}-manager"
  description  = "Service account to manage '${var.environment_name}' environment Kafka Schema Registry"
}

# Assign EnvironmentAdmin role to service account
resource "confluent_role_binding" "env_manager_admin" {
  principal   = "User:${confluent_service_account.env_manager.id}"
  role_name   = "EnvironmentAdmin"
  crn_pattern = confluent_environment.main.resource_name
}

# Use Schema Registry cluster data source
# Schema Registry cluster is automatically created when the environment is created
data "confluent_schema_registry_cluster" "essentials" {
  environment {
    id = confluent_environment.main.id
  }
}

# Create API key for Schema Registry access
resource "confluent_api_key" "schema_registry_api_key" {
  display_name = "${var.environment_name}-schema-registry-api-key"
  description  = "Schema Registry API Key for ${var.environment_name} environment"
  
  owner {
    id          = var.apikey_owner_id
    api_version = "iam/v2"
    kind        = "User"
  }

  managed_resource {
    id          = data.confluent_schema_registry_cluster.essentials.id
    api_version = data.confluent_schema_registry_cluster.essentials.api_version
    kind        = data.confluent_schema_registry_cluster.essentials.kind

    environment {
      id = confluent_environment.main.id
    }
  }
} 