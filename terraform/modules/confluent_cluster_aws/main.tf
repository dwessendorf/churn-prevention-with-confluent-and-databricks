terraform {
  required_providers {
    confluent = {
      source  = "confluentinc/confluent"
      version = "~> 1.0"
    }
  }
}

resource "confluent_kafka_cluster" "cluster" {
  display_name = var.cluster_name
  availability = "SINGLE_ZONE"
  cloud        = "AWS"
  region       = var.region
  basic {}

  environment {
    id = var.environment_id
  }
}

resource "confluent_kafka_topic" "topic" {
  kafka_cluster {
    id = confluent_kafka_cluster.cluster.id
  }
  
  topic_name    = var.topic_name
  partitions_count = 6
  rest_endpoint = confluent_kafka_cluster.cluster.rest_endpoint
  
  credentials {
    key    = confluent_api_key.kafka_api_key.id
    secret = confluent_api_key.kafka_api_key.secret
  }
}

resource "confluent_api_key" "kafka_api_key" {
  display_name = "${var.cluster_name}-api-key"
  description  = "Kafka API Key for ${var.cluster_name}"
  
  owner {
    id          = var.apikey_owner_id
    api_version = "iam/v2"
    kind        = "User"
  }

  managed_resource {
    id          = confluent_kafka_cluster.cluster.id
    api_version = confluent_kafka_cluster.cluster.api_version
    kind        = confluent_kafka_cluster.cluster.kind
    environment {
      id = var.environment_id
    }
  }
} 