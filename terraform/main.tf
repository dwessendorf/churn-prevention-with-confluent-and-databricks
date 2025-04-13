provider "aws" {
  region = var.aws_region
}

provider "confluent" {
  cloud_api_key    = var.confluent_cloud_api_key
  cloud_api_secret = var.confluent_cloud_api_secret
}

# Create Confluent Environment and Schema Registry
module "confluent_environment" {
  source = "./modules/confluent_environment"
  
  environment_name        = var.environment_name
  schema_registry_package = var.schema_registry_package
  schema_registry_region  = var.schema_registry_region
  apikey_owner_id         = var.apikey_owner_id
}

# Import existing module for Confluent Cloud
module "confluent_cluster_aws" {
  source = "./modules/confluent_cluster_aws"

  cluster_name     = var.aws_cluster_name
  region           = var.aws_region
  topic_name       = var.customer_review_kafka_topic_name
  environment_id   = module.confluent_environment.environment_id
  apikey_owner_id  = var.apikey_owner_id
}

# Create a second topic in the same cluster for the policy producer
resource "confluent_kafka_topic" "policy_topic" {
  provider = confluent

  kafka_cluster {
    id = module.confluent_cluster_aws.cluster_id
  }
  
  topic_name       = var.policy_producer_kafka_topic_name
  partitions_count = 6
  rest_endpoint    = module.confluent_cluster_aws.rest_endpoint
  
  credentials {
    key    = module.confluent_cluster_aws.api_key_id
    secret = module.confluent_cluster_aws.api_key_secret
  }
}

# Add Schema Registry with policy schema
module "schema_registry" {
  source = "./modules/confluent_schema_registry"

  environment_name              = var.environment_name
  environment_id                = module.confluent_environment.environment_id
  schema_registry_id            = module.confluent_environment.schema_registry_id
  schema_registry_rest_endpoint = module.confluent_environment.schema_registry_rest_endpoint
  schema_registry_api_key_id    = module.confluent_environment.schema_registry_api_key_id
  schema_registry_api_key_secret = module.confluent_environment.schema_registry_api_key_secret
  policy_topic_name             = var.policy_producer_kafka_topic_name
  schema_path                   = "${path.module}/schema/policy_schema.json"
}

module "customer_review_creator_lambda" {
  source = "./modules/aws_lambda"

  function_name            = var.customer_review_function_name
  region                   = var.aws_region
  runtime                  = var.runtime
  entry_point              = var.entry_point
  kafka_topic_name         = var.customer_review_kafka_topic_name
  secret_name              = var.customer_review_secret_name
  min_reviews_per_run      = var.customer_review_min_reviews_per_run
  max_reviews_per_run      = var.customer_review_max_reviews_per_run
  seconds_between_reviews  = var.customer_review_seconds_between_reviews
  source_dir               = "../aws-lambda/customer-review-creator"
  kafka_api_key_id         = module.confluent_cluster_aws.api_key_id
  kafka_api_key_secret     = module.confluent_cluster_aws.api_key_secret
  kafka_bootstrap_server   = module.confluent_cluster_aws.bootstrap_servers
}

module "policy_producer_lambda" {
  source = "./modules/aws_lambda"

  function_name            = var.policy_producer_function_name
  region                   = var.aws_region
  runtime                  = var.runtime
  entry_point              = var.entry_point
  kafka_topic_name         = var.policy_producer_kafka_topic_name
  secret_name              = var.policy_producer_secret_name
  min_reviews_per_run      = var.policy_producer_min_reviews_per_run
  max_reviews_per_run      = var.policy_producer_max_reviews_per_run
  seconds_between_reviews  = var.policy_producer_seconds_between_reviews
  source_dir               = "../aws-lambda/policy-producer"
  kafka_api_key_id         = module.confluent_cluster_aws.api_key_id
  kafka_api_key_secret     = module.confluent_cluster_aws.api_key_secret
  kafka_bootstrap_server   = module.confluent_cluster_aws.bootstrap_servers
} 